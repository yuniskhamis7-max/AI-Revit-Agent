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

    def register(self, name, description, custom_instructions=None, parameters=None):
        """Decorator to register a function as an agent-callable tool."""
        def decorator(func):
            schema = OrderedDict()
            schema["name"] = name
            schema["description"] = description
            if custom_instructions:
                schema["custom_instructions"] = custom_instructions
            schema["parameters"] = parameters or {}

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
            payload = json.loads(payload_str)
            tool_name = payload.get("tool")
            tool_input = payload.get("input") or {}

            if tool_name == "get_tools":
                discovery_res = OrderedDict([
                    ("status", "success"),
                    ("tools", self.get_schemas())
                ])
                return json.dumps(discovery_res)

            if tool_name not in self._tools:
                return json.dumps({
                    "status": "error",
                    "message": "Tool '{}' not found in registry.".format(tool_name)
                })

            doc = ui_app.ActiveUIDocument.Document
            
            # Dynamically reload submodules to pick up code edits instantly
            try:
                import sys
                if 'tools.level_tools' in sys.modules:
                    reload(sys.modules['tools.level_tools'])
                if 'tools.grid_tools' in sys.modules:
                    reload(sys.modules['tools.grid_tools'])
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
# ACTION TOOL REGISTRATION AND ROUTING
# =====================================================================

@registry.register(
    name="fetch_levels",
    description="Fetches all levels in the project, including their absolute 3D model boundary extents.",
    custom_instructions="Returns precise visual coordinates and elevations. Useful for checking horizontal reference limits before grid placement.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def fetch_levels(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    return LevelTools(doc).fetch_all()


@registry.register(
    name="fetch_grids",
    description="Fetches all gridlines in the project, including their unique IDs, labels, endpoints, and curvature details.",
    custom_instructions="Query this to understand the existing grid layout, spacing pattern, and naming convention before editing.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def fetch_grids(doc, ui_app, tool_input):
    from tools.grid_tools import GridTools
    return GridTools(doc).fetch_all()


@registry.register(
    name="create_grid",
    description="Creates a new linear gridline in the project.",
    custom_instructions="Grid names must be unique. The coordinates should align with the project envelope / level boundaries.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Unique grid label (e.g., 'A', '1')."},
            "start_x": {"type": "number", "description": "Start X coordinate in feet."},
            "start_y": {"type": "number", "description": "Start Y coordinate in feet."},
            "end_x": {"type": "number", "description": "End X coordinate in feet."},
            "end_y": {"type": "number", "description": "End Y coordinate in feet."}
        },
        "required": ["name", "start_x", "start_y", "end_x", "end_y"]
    }
)
def create_grid(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import XYZ
    from tools.grid_tools import GridTools
    
    name = str(tool_input["name"])
    start_pt = XYZ(float(tool_input["start_x"]), float(tool_input["start_y"]), 0.0)
    end_pt = XYZ(float(tool_input["end_x"]), float(tool_input["end_y"]), 0.0)
    
    view = ui_app.ActiveUIDocument.ActiveView
    return GridTools(doc).create(name, start_pt, end_pt, view)


@registry.register(
    name="modify_grid",
    description="Modifies coordinates or renames an existing gridline.",
    custom_instructions="Grid curves will only be modified if all start/end coordinates are provided. Otherwise, only rename applies.",
    parameters={
        "type": "object",
        "properties": {
            "grid_id": {"type": "string", "description": "The UniqueId of the grid to edit."},
            "name": {"type": "string", "description": "Optional new name for the grid."},
            "start_x": {"type": "number", "description": "Optional new start X (feet)."},
            "start_y": {"type": "number", "description": "Optional new start Y (feet)."},
            "end_x": {"type": "number", "description": "Optional new end X (feet)."},
            "end_y": {"type": "number", "description": "Optional new end Y (feet)."}
        },
        "required": ["grid_id"]
    }
)
def modify_grid(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import XYZ
    from tools.grid_tools import GridTools
    
    grid_id = tool_input["grid_id"]
    name = tool_input.get("name")
    
    start_pt = None
    end_pt = None
    has_coords = all(k in tool_input for k in ["start_x", "start_y", "end_x", "end_y"])
    if has_coords:
        start_pt = XYZ(float(tool_input["start_x"]), float(tool_input["start_y"]), 0.0)
        end_pt = XYZ(float(tool_input["end_x"]), float(tool_input["end_y"]), 0.0)
        
    view = ui_app.ActiveUIDocument.ActiveView
    return GridTools(doc).modify(grid_id, name=name, start_pt=start_pt, end_pt=end_pt, view=view)


@registry.register(
    name="delete_grid",
    description="Deletes an existing gridline.",
    custom_instructions="Be careful when deleting grids as they may have elements dependent on them.",
    parameters={
        "type": "object",
        "properties": {
            "grid_id": {"type": "string", "description": "The UniqueId of the target grid."}
        },
        "required": ["grid_id"]
    }
)
def delete_grid(doc, ui_app, tool_input):
    from tools.grid_tools import GridTools
    grid_id = tool_input["grid_id"]
    return GridTools(doc).delete(grid_id)


@registry.register(
    name="create_level",
    description="Creates a new horizontal datum level with options to configure custom visual extents.",
    custom_instructions="Elevation heights are in decimal feet. Provide a reference level ID when duplicating view extents of existing project configurations.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Unique name of the level (e.g., 'Level 3')."},
            "elevation": {"type": "number", "description": "Elevation height in feet."},
            "min_x": {"type": "number", "description": "Optional minimum X visual boundary in feet."},
            "min_y": {"type": "number", "description": "Optional minimum Y visual boundary in feet."},
            "max_x": {"type": "number", "description": "Optional maximum X visual boundary in feet."},
            "max_y": {"type": "number", "description": "Optional maximum Y visual boundary in feet."},
            "reference_level_id": {"type": "string", "description": "Optional UniqueId of an existing level to copy extents from across views."},
            "maximize_extents": {"type": "boolean", "description": "Option to maximize the default 3D extents. Defaults to True."}
        },
        "required": ["name", "elevation"]
    }
)
def create_level(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    
    name = str(tool_input["name"])
    elevation = float(tool_input["elevation"])
    min_x = tool_input.get("min_x")
    min_y = tool_input.get("min_y")
    max_x = tool_input.get("max_x")
    max_y = tool_input.get("max_y")
    ref_id = tool_input.get("reference_level_id")
    maximize = tool_input.get("maximize_extents", True)
    
    def to_float(val):
        return float(val) if val is not None else None
        
    return LevelTools(doc).create(
        name=name,
        elevation=elevation,
        min_x=to_float(min_x),
        min_y=to_float(min_y),
        max_x=to_float(max_x),
        max_y=to_float(max_y),
        reference_level_id=ref_id,
        maximize_extents=maximize
    )


@registry.register(
    name="modify_level",
    description="Modifies height elevation, renames, or updates the 3D/2D extents of an existing level.",
    custom_instructions="Modifying levels updates all elements attached to the level. Exercise caution when altering heights.",
    parameters={
        "type": "object",
        "properties": {
            "level_id": {"type": "string", "description": "The UniqueId of the target level."},
            "name": {"type": "string", "description": "Optional new name for the level."},
            "elevation": {"type": "number", "description": "Optional new elevation height in feet."},
            "min_x": {"type": "number", "description": "Optional new minimum X boundary in feet."},
            "min_y": {"type": "number", "description": "Optional new minimum Y boundary in feet."},
            "max_x": {"type": "number", "description": "Optional new maximum X boundary in feet."},
            "max_y": {"type": "number", "description": "Optional new maximum Y boundary in feet."},
            "reference_level_id": {"type": "string", "description": "Optional UniqueId of an existing level to copy extents from."},
            "maximize_extents": {"type": "boolean", "description": "Optional option to maximize 3D extents."}
        },
        "required": ["level_id"]
    }
)
def modify_level(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    
    level_id = tool_input["level_id"]
    name = tool_input.get("name")
    elevation = tool_input.get("elevation")
    min_x = tool_input.get("min_x")
    min_y = tool_input.get("min_y")
    max_x = tool_input.get("max_x")
    max_y = tool_input.get("max_y")
    ref_id = tool_input.get("reference_level_id")
    maximize = tool_input.get("maximize_extents")
    
    def to_float(val):
        return float(val) if val is not None else None
        
    return LevelTools(doc).modify(
        level_id=level_id,
        name=name,
        elevation=to_float(elevation),
        min_x=to_float(min_x),
        min_y=to_float(min_y),
        max_x=to_float(max_x),
        max_y=to_float(max_y),
        reference_level_id=ref_id,
        maximize_extents=maximize
    )


@registry.register(
    name="delete_level",
    description="Deletes an existing level. Deletes all associated plan views automatically.",
    custom_instructions="Revit requires at least one level to exist in the document at all times. Attempting to delete the last level will trigger an exception.",
    parameters={
        "type": "object",
        "properties": {
            "level_id": {"type": "string", "description": "The UniqueId of the target level."}
        },
        "required": ["level_id"]
    }
)
def delete_level(doc, ui_app, tool_input):
    from tools.level_tools import LevelTools
    level_id = tool_input["level_id"]
    return LevelTools(doc).delete(level_id)
