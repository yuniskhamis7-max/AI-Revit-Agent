# -*- coding: utf-8 -*-
"""Tool registry, routing engine, and tool schemas for Revit Agent Bridge."""

from collections import OrderedDict

# =====================================================================
# DECOUPLED TOOL REGISTRY & ROUTING ENGINE
# =====================================================================

class ToolRegistry(object):
    """Manages tool registration, metadata discovery, and execution dispatch."""
    def __init__(self):
        self._tools = {}

    def register(self, name, description, custom_instructions=None, parameters=None,
                 measurement_unit="feet", rotation_unit=None,
                 # ── Schema metadata fields — read by the backend at runtime ──────
                 # category:     Logical element group (e.g. "levels", "columns").
                 #               Tools sharing the same category are treated as a unit
                 #               by the backend's ModelStateManager.
                 # data_key:     Key inside result["data"] where the list lives.
                 #               Only needed on fetch_* tools (e.g. "columns").
                 # id_field:     Name of the unique-ID field in result items.
                 #               Set on delete_* tools for phantom-delete guard.
                 # name_field:   Name of the human-readable name field in input.
                 #               Set on create_* / duplicate_* for duplicate-create guard.
                 # keywords:     Trigger words in user prompt that cause selective
                 #               pre-fetching of this category. Set on fetch_* tools.
                 # name_case:    "lower" (case-insensitive) or "exact" comparison
                 #               when checking for duplicate names.
                 # always_fetch: True to always pre-fetch regardless of keywords
                 #               (use for datum categories like levels/grids).
                 category=None, data_key=None, id_field=None, name_field=None,
                 keywords=None, name_case="lower", always_fetch=False):
        """Decorator to register a function as an agent-callable tool."""
        def decorator(func):
            schema = OrderedDict()
            schema["name"] = name
            schema["description"] = description
            if custom_instructions:
                schema["custom_instructions"] = custom_instructions
            if measurement_unit:
                schema["measurement_unit"] = measurement_unit
            if rotation_unit:
                schema["rotation_unit"] = rotation_unit
            schema["parameters"] = parameters or {}

            # Emit metadata into schema so the backend can read it dynamically
            if category:     schema["category"]     = category
            if data_key:     schema["data_key"]     = data_key
            if id_field:     schema["id_field"]     = id_field
            if name_field:   schema["name_field"]   = name_field
            if keywords:     schema["keywords"]     = list(keywords)
            if name_case:    schema["name_case"]    = name_case
            if always_fetch: schema["always_fetch"] = always_fetch

            self._tools[name] = {
                "callable": func,
                "schema": schema
            }
            return func
        return decorator

    def get_schemas(self):
        """Returns registered schemas for the GET /tools discovery endpoint."""
        return [data["schema"] for data in self._tools.values()]

    def execute(self, ui_app, payload_str):
        """Parses the payload, routes to the tool, and returns a JSON string."""
        import json
        try:
            # Self-healing package reload to pick up new tools on disk
            try:
                import sys
                import tools
                if 'tools' in sys.modules:
                    reload(sys.modules['tools'])
                    self._tools.update(sys.modules['tools'].registry._tools)
            except Exception:
                pass

            payload = json.loads(payload_str)
            tool_name = payload.get("tool")
            tool_input = payload.get("input") or {}

            if tool_name == "get_tools":
                reload_err = None
                try:
                    import sys
                    self._tools.clear()
                    if 'tools' in sys.modules:
                        reload(sys.modules['tools'])
                        new_registry = sys.modules['tools'].registry
                        self._tools.update(new_registry._tools)
                    else:
                        reload_err = "tools not in sys.modules"
                except Exception as ex:
                    reload_err = "Reload exception: " + str(ex)

                discovery_res = OrderedDict([
                    ("status", "success"),
                    ("tools", self.get_schemas())
                ])
                if reload_err:
                    discovery_res["reload_error"] = reload_err
                return json.dumps(discovery_res)

            if tool_name not in self._tools:
                return json.dumps({
                    "status": "error",
                    "message": "Tool '{}' not found in registry.".format(tool_name)
                })

            doc = ui_app.ActiveUIDocument.Document

            # Auto-reload all tool submodules to pick up code edits instantly.
            # Uses pkgutil so any new *_tools.py file is discovered automatically —
            # no manual list maintenance required.
            try:
                import sys
                import pkgutil
                import tools as _tools_pkg
                for _importer, _modname, _ispkg in pkgutil.iter_modules(_tools_pkg.__path__):
                    _full_name = 'tools.' + _modname
                    if _full_name in sys.modules:
                        reload(sys.modules[_full_name])
            except Exception:
                pass

            tool_fn = self._tools[tool_name]["callable"]
            result = tool_fn(doc, ui_app, tool_input)
            return json.dumps(result)

        except Exception as ex:
            return json.dumps({
                "status": "error",
                "message": "Python routing system exception: {}".format(str(ex))
            })


registry = ToolRegistry()

# =====================================================================
# SHARED PARAMETER DEFINITIONS
# =====================================================================

# Shared 'unit' parameter definition — added to all measurement-accepting tools.
_UNIT_PARAM = {
    "type": "string",
    "description": (
        "Unit of all numeric measurement values in this call. "
        "Supported: 'feet', 'meters', 'mm', 'cm', 'inches'. Defaults to 'feet'."
    )
}


# =====================================================================
# LEVEL TOOLS
# =====================================================================

@registry.register(
    name="fetch_levels",
    description="Fetches all levels in the project, including their absolute 3D model boundary extents. Coordinates and elevations can be converted to the specified unit.",
    custom_instructions="Returns precise visual coordinates and elevations. If different levels have different boundary extents in the model, you MUST ask the user which level's extents the grids should fit before creating or modifying grids.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {"unit": _UNIT_PARAM},
        "required": []
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="levels",
    data_key="levels",
    keywords=["level", "elevation", "height", "storey", "datum", "room", "space", "area"],
    always_fetch=True,
)
def fetch_levels(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    unit = tool_input.get("unit", "feet")
    return LevelTools(doc).fetch_all(unit)


@registry.register(
    name="fetch_grids",
    description="Fetches all gridlines in the project, including their unique IDs, labels, endpoints, and curvature details. Coordinates and arc radii can be converted to the specified unit.",
    custom_instructions="Query this to understand the existing grid layout, spacing pattern, and naming convention before editing.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {"unit": _UNIT_PARAM},
        "required": []
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="grids",
    data_key="grids",
    keywords=["grid", "axis", "gridline", "spacing", "wall", "partition", "floor", "slab", "ceiling", "roof"],
    always_fetch=True,
)
def fetch_grids(doc, ui_app, tool_input):
    from tools.grid_tools import GridTools
    unit = tool_input.get("unit", "feet")
    return GridTools(doc).fetch_all(unit)


@registry.register(
    name="create_grid",
    description="Creates a new linear gridline in the project.",
    custom_instructions="Grid names must be unique. The coordinates should align with the project envelope / level boundaries. Do NOT ask redundant, obvious, or unnecessary questions about dimensions, count, spacing, or coordinate origin alignment if they can be determined directly from the level extents or existing grids. WARNING SCENARIO: Creating a grid line with the same name as an existing grid line will trigger an exception. Always check existing grids and delete duplicates before creating.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Unique grid label (e.g., 'A', '1')."},
            "start_x": {"type": "number", "description": "Start X coordinate."},
            "start_y": {"type": "number", "description": "Start Y coordinate."},
            "end_x": {"type": "number", "description": "End X coordinate."},
            "end_y": {"type": "number", "description": "End Y coordinate."},
            "unit": _UNIT_PARAM
        },
        "required": ["name", "start_x", "start_y", "end_x", "end_y"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="grids",
    name_field="name",
    name_case="exact",
)
def create_grid(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import XYZ
    from tools.grid_tools import GridTools
    from tools.utils import convert_to_feet

    unit = tool_input.get("unit", "feet")
    name = str(tool_input["name"])
    sx = convert_to_feet(tool_input["start_x"], unit)
    sy = convert_to_feet(tool_input["start_y"], unit)
    ex = convert_to_feet(tool_input["end_x"], unit)
    ey = convert_to_feet(tool_input["end_y"], unit)
    start_pt = XYZ(sx, sy, 0.0)
    end_pt = XYZ(ex, ey, 0.0)

    view = ui_app.ActiveUIDocument.ActiveView
    return GridTools(doc).create(name, start_pt, end_pt, view)


@registry.register(
    name="modify_grid",
    description="Modifies coordinates or renames an existing gridline.",
    custom_instructions="Grid curves will only be modified if all start/end coordinates are provided. Otherwise, only rename applies. Do NOT ask redundant, obvious, or unnecessary questions about dimensions, count, spacing, or coordinate origin alignment if they can be determined directly from the level extents or existing grids.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "grid_id": {"type": "string", "description": "The UniqueId of the grid to edit."},
            "name": {"type": "string", "description": "Optional new name for the grid."},
            "start_x": {"type": "number", "description": "Optional new start X coordinate."},
            "start_y": {"type": "number", "description": "Optional new start Y coordinate."},
            "end_x": {"type": "number", "description": "Optional new end X coordinate."},
            "end_y": {"type": "number", "description": "Optional new end Y coordinate."},
            "unit": _UNIT_PARAM
        },
        "required": ["grid_id"]
    },
    category="grids",
)
def modify_grid(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import XYZ
    from tools.grid_tools import GridTools
    from tools.utils import convert_to_feet

    grid_id = tool_input["grid_id"]
    name = tool_input.get("name")

    coord_keys = ["start_x", "start_y", "end_x", "end_y"]
    has_any_coords = any(k in tool_input for k in coord_keys)

    start_pt = None
    end_pt = None

    if has_any_coords:
        unit = tool_input.get("unit", "feet")
        grid = doc.GetElement(grid_id)
        if grid and grid.Curve and grid.Curve.IsBound:
            curr_start = grid.Curve.GetEndPoint(0)
            curr_end = grid.Curve.GetEndPoint(1)

            x0 = convert_to_feet(tool_input["start_x"], unit) if "start_x" in tool_input else curr_start.X
            y0 = convert_to_feet(tool_input["start_y"], unit) if "start_y" in tool_input else curr_start.Y
            x1 = convert_to_feet(tool_input["end_x"], unit) if "end_x" in tool_input else curr_end.X
            y1 = convert_to_feet(tool_input["end_y"], unit) if "end_y" in tool_input else curr_end.Y

            start_pt = XYZ(x0, y0, 0.0)
            end_pt = XYZ(x1, y1, 0.0)

    view = ui_app.ActiveUIDocument.ActiveView
    return GridTools(doc).modify(grid_id, name=name, start_pt=start_pt, end_pt=end_pt, view=view)


@registry.register(
    name="delete_grid",
    description="Deletes an existing gridline.",
    custom_instructions="Be careful when deleting grids as they may have elements dependent on them.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "grid_id": {"type": "string", "description": "The UniqueId of the target grid."}
        },
        "required": ["grid_id"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="grids",
    id_field="grid_id",
)
def delete_grid(doc, ui_app, tool_input):
    from tools.grid_tools import GridTools
    grid_id = tool_input["grid_id"]
    return GridTools(doc).delete(grid_id)


@registry.register(
    name="create_level",
    description="Creates a new horizontal datum level with options to configure custom visual extents.",
    custom_instructions="Elevation heights are numeric. Provide a reference level ID when duplicating view extents of existing project configurations. When replacing levels: CREATE new levels FIRST, THEN delete old ones. Never delete all levels before creating replacements. WARNING SCENARIO: Level names must be unique. Creating a level with the same name as an existing level will trigger an exception. Verify existing level names first.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Unique name of the level (e.g., 'Level 3')."},
            "elevation": {"type": "number", "description": "Elevation height."},
            "min_x": {"type": "number", "description": "Optional minimum X visual boundary."},
            "min_y": {"type": "number", "description": "Optional minimum Y visual boundary."},
            "max_x": {"type": "number", "description": "Optional maximum X visual boundary."},
            "max_y": {"type": "number", "description": "Optional maximum Y visual boundary."},
            "reference_level_id": {"type": "string", "description": "Optional UniqueId of an existing level to copy extents from across views."},
            "maximize_extents": {"type": "boolean", "description": "Option to maximize the default 3D extents. Defaults to True."},
            "unit": _UNIT_PARAM
        },
        "required": ["name", "elevation"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="levels",
    name_field="name",
    name_case="lower",
)
def create_level(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    from tools.utils import convert_to_feet

    unit = tool_input.get("unit", "feet")
    name = str(tool_input["name"])
    elevation = convert_to_feet(tool_input["elevation"], unit)
    min_x = convert_to_feet(tool_input["min_x"], unit) if tool_input.get("min_x") is not None else None
    min_y = convert_to_feet(tool_input["min_y"], unit) if tool_input.get("min_y") is not None else None
    max_x = convert_to_feet(tool_input["max_x"], unit) if tool_input.get("max_x") is not None else None
    max_y = convert_to_feet(tool_input["max_y"], unit) if tool_input.get("max_y") is not None else None
    ref_id = tool_input.get("reference_level_id")
    maximize = tool_input.get("maximize_extents", True)

    return LevelTools(doc).create(
        name=name,
        elevation=elevation,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        reference_level_id=ref_id,
        maximize_extents=maximize
    )


@registry.register(
    name="modify_level",
    description="Modifies height elevation, renames, or updates the 3D/2D extents of an existing level.",
    custom_instructions="Modifying levels updates all elements attached to the level. Exercise caution when altering heights.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "level_id": {"type": "string", "description": "The UniqueId of the target level."},
            "name": {"type": "string", "description": "Optional new name for the level."},
            "elevation": {"type": "number", "description": "Optional new elevation height."},
            "min_x": {"type": "number", "description": "Optional new minimum X boundary."},
            "min_y": {"type": "number", "description": "Optional new minimum Y boundary."},
            "max_x": {"type": "number", "description": "Optional new maximum X boundary."},
            "max_y": {"type": "number", "description": "Optional new maximum Y boundary."},
            "reference_level_id": {"type": "string", "description": "Optional UniqueId of an existing level to copy extents from."},
            "maximize_extents": {"type": "boolean", "description": "Optional option to maximize 3D extents."},
            "unit": _UNIT_PARAM
        },
        "required": ["level_id"]
    },
    category="levels",
)
def modify_level(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    from tools.utils import convert_to_feet

    unit = tool_input.get("unit", "feet")
    level_id = tool_input["level_id"]
    name = tool_input.get("name")
    elevation = convert_to_feet(tool_input["elevation"], unit) if tool_input.get("elevation") is not None else None
    min_x = convert_to_feet(tool_input["min_x"], unit) if tool_input.get("min_x") is not None else None
    min_y = convert_to_feet(tool_input["min_y"], unit) if tool_input.get("min_y") is not None else None
    max_x = convert_to_feet(tool_input["max_x"], unit) if tool_input.get("max_x") is not None else None
    max_y = convert_to_feet(tool_input["max_y"], unit) if tool_input.get("max_y") is not None else None
    ref_id = tool_input.get("reference_level_id")
    maximize = tool_input.get("maximize_extents")

    return LevelTools(doc).modify(
        level_id=level_id,
        name=name,
        elevation=elevation,
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        reference_level_id=ref_id,
        maximize_extents=maximize
    )


@registry.register(
    name="delete_level",
    description="Deletes an existing level. Deletes all associated plan views automatically.",
    custom_instructions="Revit requires at least one level to exist in the document at all times. Attempting to delete the last level will trigger an exception. When replacing levels: CREATE new levels FIRST, THEN delete old ones. Never delete all levels before creating replacements.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "level_id": {"type": "string", "description": "The UniqueId of the target level."}
        },
        "required": ["level_id"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="levels",
    id_field="level_id",
)
def delete_level(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    level_id = tool_input["level_id"]
    return LevelTools(doc).delete(level_id, ui_app)


# =====================================================================
# STRUCTURAL COLUMN TOOLS
# =====================================================================

@registry.register(
    name="fetch_structural_columns",
    description="Fetches all structural columns in the project, including their location coordinates, base/top levels, base/top offsets, rotation, and type information. Coordinates and offsets can be converted to the specified unit.",
    measurement_unit="feet",
    rotation_unit="degrees",
    parameters={
        "type": "object",
        "properties": {"unit": _UNIT_PARAM},
        "required": []
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="columns",
    data_key="columns",
    keywords=["column", "pillar", "post", "structural"],
)
def fetch_structural_columns(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    unit = tool_input.get("unit", "feet")
    return ColumnTools(doc).fetch_all(unit)


@registry.register(
    name="fetch_structural_column_types",
    description="Fetches all loaded structural column family types, including their names and unique type IDs.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="column_types",
    data_key="column_types",
    keywords=["column type", "column family", "section", "profile"],
)
def fetch_structural_column_types(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    return ColumnTools(doc).fetch_types()


@registry.register(
    name="create_structural_column",
    description="Creates a new vertical structural column at specific 2D coordinates. Location and offsets are specified in feet; rotation angle is in degrees.",
    custom_instructions="To place structural columns at grid intersections (a standard AEC practice), first query existing grid coordinates using the appropriate fetch tool, calculate the intersection point, and pass it to this tool. WARNING SCENARIO: Placing a structural column at the exact same coordinates (X, Y) as an existing column will trigger a Revit identical instances warning. To avoid duplicate counting and warnings, always verify existing column coordinates and delete duplicates before creating.",
    measurement_unit="feet",
    rotation_unit="degrees",
    parameters={
        "type": "object",
        "properties": {
            "x": {"type": "number", "description": "X coordinate in feet."},
            "y": {"type": "number", "description": "Y coordinate in feet."},
            "base_level_id": {"type": "string", "description": "UniqueId or Name of the base level."},
            "top_level_id": {"type": "string", "description": "Optional UniqueId or Name of the top level."},
            "base_offset": {"type": "number", "description": "Optional base level offset in feet. Defaults to 0.0."},
            "top_offset": {"type": "number", "description": "Optional top level offset in feet. Defaults to 0.0."},
            "rotation_degrees": {"type": "number", "description": "Optional rotation angle in degrees around Z axis. Defaults to 0.0."},
            "column_type_id": {"type": "string", "description": "Optional UniqueId or name of structural column family symbol. Omit to use default."},
            "unit": _UNIT_PARAM
        },
        "required": ["x", "y", "base_level_id"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    # Columns don't use a name field for duplicate detection (they're position-based),
    # but we still set id_field so the backend tracks created element IDs.
    category="columns",
    id_field="column_id",
)
def create_structural_column(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    from tools.utils import convert_to_feet

    unit = tool_input.get("unit", "feet")
    x = convert_to_feet(tool_input["x"], unit)
    y = convert_to_feet(tool_input["y"], unit)
    base_level_id = str(tool_input["base_level_id"])
    top_level_id = tool_input.get("top_level_id")
    base_offset = convert_to_feet(tool_input.get("base_offset", 0.0), unit)
    top_offset = convert_to_feet(tool_input.get("top_offset", 0.0), unit)
    rotation_degrees = tool_input.get("rotation_degrees", 0.0)
    column_type_id = tool_input.get("column_type_id")

    return ColumnTools(doc).create(
        x=x,
        y=y,
        base_level_id=base_level_id,
        top_level_id=top_level_id,
        base_offset=base_offset,
        top_offset=top_offset,
        rotation_degrees=rotation_degrees,
        column_type_id=column_type_id
    )


@registry.register(
    name="modify_structural_column",
    description="Modifies attributes (location, levels, offsets, rotation, type) of an existing structural column instance. Location and offsets are specified in feet; rotation angle is in degrees.",
    measurement_unit="feet",
    rotation_unit="degrees",
    parameters={
        "type": "object",
        "properties": {
            "column_id": {"type": "string", "description": "UniqueId of the target structural column instance."},
            "x": {"type": "number", "description": "Optional new X coordinate in feet."},
            "y": {"type": "number", "description": "Optional new Y coordinate in feet."},
            "base_level_id": {"type": "string", "description": "Optional UniqueId or Name of new base level."},
            "top_level_id": {"type": "string", "description": "Optional UniqueId or Name of new top level."},
            "base_offset": {"type": "number", "description": "Optional new base offset in feet."},
            "top_offset": {"type": "number", "description": "Optional new top offset in feet."},
            "rotation_degrees": {"type": "number", "description": "Optional new absolute rotation in degrees around Z axis."},
            "column_type_id": {"type": "string", "description": "Optional new structural column type UniqueId or name."},
            "unit": _UNIT_PARAM
        },
        "required": ["column_id"]
    },
    category="columns",
)
def modify_structural_column(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    from tools.utils import convert_to_feet

    unit = tool_input.get("unit", "feet")
    column_id = tool_input["column_id"]
    x = convert_to_feet(tool_input["x"], unit) if tool_input.get("x") is not None else None
    y = convert_to_feet(tool_input["y"], unit) if tool_input.get("y") is not None else None
    base_level_id = tool_input.get("base_level_id")
    top_level_id = tool_input.get("top_level_id")
    base_offset = convert_to_feet(tool_input["base_offset"], unit) if tool_input.get("base_offset") is not None else None
    top_offset = convert_to_feet(tool_input["top_offset"], unit) if tool_input.get("top_offset") is not None else None
    rotation_degrees = tool_input.get("rotation_degrees")
    column_type_id = tool_input.get("column_type_id")

    return ColumnTools(doc).modify(
        column_id=column_id,
        x=x,
        y=y,
        base_level_id=base_level_id,
        top_level_id=top_level_id,
        base_offset=base_offset,
        top_offset=top_offset,
        rotation_degrees=float(rotation_degrees) if rotation_degrees is not None else None,
        column_type_id=column_type_id
    )


@registry.register(
    name="delete_structural_column",
    description="Deletes an existing structural column instance.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "column_id": {"type": "string", "description": "UniqueId of the structural column to delete."}
        },
        "required": ["column_id"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="columns",
    id_field="column_id",
)
def delete_structural_column(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    column_id = tool_input["column_id"]
    return ColumnTools(doc).delete(column_id)


@registry.register(
    name="duplicate_structural_column_type",
    description="Duplicates an existing structural column type and modifies its dimensions (type parameters). The dimensions dictionary maps parameter names to values in feet.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "column_type_id": {"type": "string", "description": "UniqueId or Name of the source type to duplicate."},
            "new_type_name": {"type": "string", "description": "Name for the duplicated type."},
            "dimensions": {
                "type": "object",
                "description": "Optional dictionary of type parameter names mapping to float values in feet.",
                "additionalProperties": {"type": "number"}
            },
            "unit": _UNIT_PARAM
        },
        "required": ["column_type_id", "new_type_name"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    # new_type_name is the field the backend checks for duplicate-create guard.
    category="column_types",
    name_field="new_type_name",
    name_case="lower",
)
def duplicate_structural_column_type(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    from tools.utils import convert_to_feet

    unit = tool_input.get("unit", "feet")
    column_type_id = tool_input["column_type_id"]
    new_type_name = tool_input["new_type_name"]
    raw_dims = tool_input.get("dimensions") or {}
    dimensions = {}
    for k, v in raw_dims.items():
        dimensions[k] = convert_to_feet(v, unit)

    return ColumnTools(doc).duplicate_type(column_type_id, new_type_name, dimensions)


@registry.register(
    name="modify_structural_column_type",
    description="Modifies the type parameters (dimensions) of an existing structural column family type. The dimensions dictionary maps parameter names to values in feet.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "column_type_id": {"type": "string", "description": "UniqueId or Name of structural column type to edit."},
            "dimensions": {
                "type": "object",
                "description": "Dictionary of type parameter names mapping to float values in feet.",
                "additionalProperties": {"type": "number"}
            },
            "unit": _UNIT_PARAM
        },
        "required": ["column_type_id", "dimensions"]
    },
    category="column_types",
)
def modify_structural_column_type(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    from tools.utils import convert_to_feet

    unit = tool_input.get("unit", "feet")
    column_type_id = tool_input["column_type_id"]
    raw_dims = tool_input["dimensions"]
    dimensions = {}
    for k, v in raw_dims.items():
        dimensions[k] = convert_to_feet(v, unit)

    return ColumnTools(doc).modify_type(column_type_id, dimensions)


@registry.register(
    name="delete_structural_column_type",
    description="Deletes a structural column type from the project document.",
    measurement_unit="feet",
    parameters={
        "type": "object",
        "properties": {
            "column_type_id": {"type": "string", "description": "UniqueId of target structural column type to delete."}
        },
        "required": ["column_type_id"]
    },
    # ── metadata ──────────────────────────────────────────────────────────────
    category="column_types",
    id_field="column_type_id",
)
def delete_structural_column_type(doc, ui_app, tool_input):
    from tools.column_tools import ColumnTools
    column_type_id = tool_input["column_type_id"]
    return ColumnTools(doc).delete_type(column_type_id)


# =====================================================================
# BATCH EXECUTION (meta-tool — no category)
# =====================================================================

@registry.register(
    name="execute_batch",
    description="Executes a list of BIM tool operations sequentially inside a single transaction group. If any operation fails, the entire batch is rolled back.",
    custom_instructions="Use this to execute multiple element modifications (e.g. creating levels, grids, or columns) in a single run.",
    parameters={
        "type": "object",
        "properties": {
            "calls": {
                "type": "array",
                "description": "List of tool calls to execute sequentially.",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool": {"type": "string", "description": "The name of the tool to call."},
                        "input": {"type": "object", "description": "The input parameters for the tool."}
                    },
                    "required": ["tool", "input"]
                }
            }
        },
        "required": ["calls"]
    }
)
def execute_batch(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import TransactionGroup
    from collections import OrderedDict

    calls = tool_input.get("calls", [])
    if not calls:
        return OrderedDict([
            ("status", "error"),
            ("message", "Empty batch request: no calls provided.")
        ])

    tg = TransactionGroup(doc, "Agent - Execute Batch")
    tg.Start()

    results = []
    success = True
    error_message = None

    try:
        for idx, call in enumerate(calls):
            t_name = call.get("tool")
            t_input = call.get("input") or {}

            if t_name == "execute_batch":
                success = False
                error_message = "Nested execute_batch calls are not allowed."
                break

            if t_name not in registry._tools:
                success = False
                error_message = "Tool '{}' (call index {}) not found in registry.".format(t_name, idx)
                break

            tool_fn = registry._tools[t_name]["callable"]

            try:
                res = tool_fn(doc, ui_app, t_input)
            except Exception as e:
                res = {"status": "error", "message": "Python tool execution exception: " + str(e)}

            results.append(OrderedDict([
                ("tool", t_name),
                ("input", t_input),
                ("result", res)
            ]))

            if isinstance(res, dict) and res.get("status") == "error":
                success = False
                error_message = "Tool '{}' at index {} failed: {}".format(
                    t_name, idx, res.get("message", "No error message")
                )
                break

        if success:
            tg.Assimilate()
            return OrderedDict([
                ("status", "success"),
                ("message", "Successfully executed all {} batch operations.".format(len(calls))),
                ("measurement_unit", "feet"),
                ("data", OrderedDict([("results", results)]))
            ])
        else:
            tg.RollBack()
            return OrderedDict([
                ("status", "error"),
                ("message", "Batch aborted and rolled back. " + error_message),
                ("data", OrderedDict([("results", results)]))
            ])

    except Exception as ex:
        try:
            tg.RollBack()
        except Exception:
            pass
        return OrderedDict([
            ("status", "error"),
            ("message", "Batch system runtime exception: " + str(ex)),
            ("data", OrderedDict([("results", results)]))
        ])
