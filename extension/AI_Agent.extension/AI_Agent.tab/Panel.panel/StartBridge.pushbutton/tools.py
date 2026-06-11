# -*- coding: utf-8 -*-
"""Tool registry and Autodesk Revit datum tool definitions."""

from collections import OrderedDict
from Autodesk.Revit.DB import *

# =====================================================================
# DECOUPLED TOOL REGISTRY & ROUTING ENGINE
# =====================================================================

class ToolRegistry(object):
    """Manages tool registration, metadata discovery, and execution dispatch."""
    def __init__(self):
        self._tools = {}

    def register(self, name, description, parameters):
        """Decorator to register a function as an agent-callable tool."""
        def decorator(func):
            schema = OrderedDict()
            schema["name"] = name
            schema["description"] = description
            schema["parameters"] = parameters

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
                    "status", "error",
                    "message", "Tool '{}' not found in registry.".format(tool_name)
                })

            doc = ui_app.ActiveUIDocument.Document
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
# GEOMETRIC EXTENT HELPER FUNCTIONS
# =====================================================================

def clip_line_to_bbox_2d(p_x, p_y, d_x, d_y, min_x, min_y, max_x, max_y):
    """Clips a 2D line defined by point P and direction D inside a 2D bounding box."""
    t_min = float('-inf')
    t_max = float('inf')
    
    # Clip against X boundaries
    if abs(d_x) < 1e-9:
        if p_x < min_x or p_x > max_x:
            return None
    else:
        t1 = (min_x - p_x) / d_x
        t2 = (max_x - p_x) / d_x
        t_min = max(t_min, min(t1, t2))
        t_max = min(t_max, max(t1, t2))
        
    # Clip against Y boundaries
    if abs(d_y) < 1e-9:
        if p_y < min_y or p_y > max_y:
            return None
    else:
        t1 = (min_y - p_y) / d_y
        t2 = (max_y - p_y) / d_y
        t_min = max(t_min, min(t1, t2))
        t_max = min(t_max, max(t1, t2))
        
    if t_min > t_max:
        return None
        
    return t_min, t_max


def apply_level_extents_to_views(doc, level, min_x, min_y, max_x, max_y):
    """Updates level extents inside all Elevation and Section views to match horizontal coordinates."""
    views = FilteredElementCollector(doc).OfClass(ViewSection).ToElements()
    
    x0, x1 = min(min_x, max_x), max(min_x, max_x)
    y0, y1 = min(min_y, max_y), max(min_y, max_y)
    elevation = level.Elevation
    
    for v in views:
        if v.IsTemplate:
            continue
        if not level.CanBeVisibleInView(v):
            continue
            
        n = v.ViewDirection
        origin = v.Origin
        
        # Calculate coordinate on the projection plane
        denom_y = abs(n.Y)
        denom_x = abs(n.X)
        
        if denom_y > 1e-9:
            p_x = origin.X
            p_y = origin.Y - n.Z * (elevation - origin.Z) / n.Y
        elif denom_x > 1e-9:
            p_x = origin.X - n.Z * (elevation - origin.Z) / n.X
            p_y = origin.Y
        else:
            continue
            
        p = XYZ(p_x, p_y, elevation)
        
        # Determine the horizontal direction vector of the Level line in this view
        z_axis = XYZ(0, 0, 1)
        d = n.CrossProduct(z_axis).Normalize()
        
        clip_res = clip_line_to_bbox_2d(p.X, p.Y, d.X, d.Y, x0, y0, x1, y1)
        if not clip_res:
            continue
            
        t_min, t_max = clip_res
        pt_start = p + d * t_min
        pt_end = p + d * t_max
        
        try:
            new_curve = Line.CreateBound(pt_start, pt_end)
            for extent_type in [DatumExtentType.Model, DatumExtentType.ViewSpecific]:
                try:
                    level.SetCurveInView(extent_type, v, new_curve)
                except Exception:
                    pass
        except Exception:
            pass


def copy_level_extents(doc, ref_level, target_level):
    """Copies both Model and View-specific extents from a reference level to target level."""
    views = FilteredElementCollector(doc).OfClass(ViewSection).ToElements()
    elevation_diff = target_level.Elevation - ref_level.Elevation
    translation_vector = XYZ(0, 0, elevation_diff)
    translation_transform = Transform.CreateTranslation(translation_vector)
    
    for v in views:
        if v.IsTemplate:
            continue
        if ref_level.CanBeVisibleInView(v) and target_level.CanBeVisibleInView(v):
            for extent_type in [DatumExtentType.Model, DatumExtentType.ViewSpecific]:
                try:
                    ref_curves = ref_level.GetCurvesInView(extent_type, v)
                    if ref_curves:
                        ref_curve = ref_curves[0]
                        target_curve = ref_curve.CreateTransformed(translation_transform)
                        target_level.SetCurveInView(extent_type, v, target_curve)
                except Exception:
                    pass

# =====================================================================
# CORE QUERY TOOLS
# =====================================================================

@registry.register(
    name="fetch_levels",
    description="Fetches all levels in the project, including their absolute 3D model boundary extents.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def fetch_levels(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import FilteredElementCollector, Level, BuiltInCategory
    from collections import OrderedDict
    
    # Calculate the actual physical building envelope/extents
    envelope_categories = [
        BuiltInCategory.OST_Walls,
        BuiltInCategory.OST_Floors,
        BuiltInCategory.OST_Roofs,
        BuiltInCategory.OST_StructuralColumns,
        BuiltInCategory.OST_StructuralFraming,
        BuiltInCategory.OST_StructuralFoundation,
        BuiltInCategory.OST_GenericModel,
        BuiltInCategory.OST_Grids
    ]
    
    min_x = min_y = float('inf')
    max_x = max_y = float('-inf')
    has_geometry = False
    
    # Union the bounding boxes of all envelope-defining elements
    for cat in envelope_categories:
        try:
            elements = FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType().ToElements()
            for el in elements:
                bbox = el.get_BoundingBox(None)
                if bbox:
                    pt0 = bbox.Min
                    pt1 = bbox.Max
                    
                    if pt0.X < min_x: min_x = pt0.X
                    if pt0.Y < min_y: min_y = pt0.Y
                    if pt1.X > max_x: max_x = pt1.X
                    if pt1.Y > max_y: max_y = pt1.Y
                    has_geometry = True
        except Exception:
            continue

    levels = FilteredElementCollector(doc).OfClass(Level)
    levels_data = []
    
    for lvl in levels:
        # Determine the unique 3D bounding box coordinates of the level
        lvl_bbox = lvl.get_BoundingBox(None)
        if lvl_bbox:
            lvl_min_x = lvl_bbox.Min.X
            lvl_min_y = lvl_bbox.Min.Y
            lvl_max_x = lvl_bbox.Max.X
            lvl_max_y = lvl_bbox.Max.Y
        elif has_geometry:
            # Fallback to model footprint envelope
            lvl_min_x = min_x
            lvl_min_y = min_y
            lvl_max_x = max_x
            lvl_max_y = max_y
        else:
            # Sane absolute fallback bounds
            lvl_min_x = 0.0
            lvl_min_y = 0.0
            lvl_max_x = 100.0
            lvl_max_y = 100.0

        start_coords = OrderedDict([
            ("x", round(lvl_min_x, 3)),
            ("y", round(lvl_min_y, 3)),
            ("z", round(lvl.Elevation, 3))
        ])
        end_coords = OrderedDict([
            ("x", round(lvl_max_x, 3)),
            ("y", round(lvl_max_y, 3)),
            ("z", round(lvl.Elevation, 3))
        ])
        
        lvl_dict = OrderedDict([
            ("name", lvl.Name),
            ("level_id", lvl.UniqueId),
            ("elevation", round(lvl.Elevation, 3)),
            ("model_extent_start", start_coords),
            ("model_extent_end", end_coords)
        ])
        
        levels_data.append(lvl_dict)
        
    res_envelope = OrderedDict([
        ("status", "success"),
        ("message", "Successfully fetched levels with precise visual bounds."),
        ("data", OrderedDict([("levels", levels_data)]))
    ])
    
    return res_envelope


@registry.register(
    name="fetch_grids",
    description="Fetches all gridlines in the project, including their unique IDs, labels, endpoints, and curvature details.",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    }
)
def fetch_grids(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import FilteredElementCollector, Grid, Line, Arc
    from collections import OrderedDict
    
    grids = FilteredElementCollector(doc).OfClass(Grid).WhereElementIsNotElementType().ToElements()
    grids_data = []
    
    for g in grids:
        g_curve = g.Curve
        is_curved = not isinstance(g_curve, Line)
        
        start_pt = None
        end_pt = None
        center_pt = None
        radius = None
        
        if g_curve:
            if g_curve.IsBound:
                start_pt = g_curve.GetEndPoint(0)
                end_pt = g_curve.GetEndPoint(1)
            
            if isinstance(g_curve, Arc):
                center_pt = g_curve.Center
                radius = g_curve.Radius

        # Format start coordinates
        start_coords = None
        if start_pt:
            start_coords = OrderedDict([
                ("x", round(start_pt.X, 3)),
                ("y", round(start_pt.Y, 3)),
                ("z", round(start_pt.Z, 3))
            ])

        # Format end coordinates
        end_coords = None
        if end_pt:
            end_coords = OrderedDict([
                ("x", round(end_pt.X, 3)),
                ("y", round(end_pt.Y, 3)),
                ("z", round(end_pt.Z, 3))
            ])

        # Format arc/curved geometry parameters if applicable
        arc_details = None
        if is_curved and center_pt and radius is not None:
            arc_details = OrderedDict([
                ("center_x", round(center_pt.X, 3)),
                ("center_y", round(center_pt.Y, 3)),
                ("center_z", round(center_pt.Z, 3)),
                ("radius", round(radius, 3))
            ])
        
        grid_dict = OrderedDict([
            ("name", g.Name),
            ("grid_id", g.UniqueId),
            ("is_curved", is_curved),
            ("pinned", g.Pinned),
            ("start_coords", start_coords),
            ("end_coords", end_coords),
            ("arc_details", arc_details)
        ])
        
        grids_data.append(grid_dict)
        
    res_payload = OrderedDict([
        ("status", "success"),
        ("message", "Successfully fetched all project grids."),
        ("data", OrderedDict([("grids", grids_data)]))
    ])
    
    return res_payload

# =====================================================================
# ACTION TOOLS (Grid & Level Operations)
# =====================================================================

@registry.register(
    name="create_grid",
    description="Creates a new linear gridline in the project.",
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
    from Autodesk.Revit.DB import Transaction, XYZ, Line, Grid, FilteredElementCollector
    from collections import OrderedDict
    name = str(tool_input["name"])
    start_pt = XYZ(float(tool_input["start_x"]), float(tool_input["start_y"]), 0.0)
    end_pt = XYZ(float(tool_input["end_x"]), float(tool_input["end_y"]), 0.0)

    for g in FilteredElementCollector(doc).OfClass(Grid):
        if g.Name.lower() == name.lower():
            return {"status": "error", "message": "Grid name '{}' already exists.".format(name)}

    with Transaction(doc, "Agent - Create Grid") as trans:
        trans.Start()
        try:
            line = Line.CreateBound(start_pt, end_pt)
            new_grid = Grid.Create(doc, line)
            new_grid.Name = name
            new_grid.Maximize3DExtents()
            new_grid.Pinned = True
            trans.Commit()
            
            return OrderedDict([
                ("status", "success"),
                ("message", "Grid '{}' successfully created.".format(name)),
                ("data", OrderedDict([("element_id", new_grid.UniqueId)]))
            ])
        except Exception as ex:
            trans.RollBack()
            return {"status": "error", "message": "Failed to create grid: " + str(ex)}


@registry.register(
    name="modify_grid",
    description="Modifies coordinates or renames an existing gridline.",
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
    from Autodesk.Revit.DB import Transaction, XYZ, Line, Grid
    from collections import OrderedDict
    grid_id = tool_input["grid_id"]
    grid = doc.GetElement(grid_id)

    if not grid or not isinstance(grid, Grid):
        return {"status": "error", "message": "Grid element not found."}

    with Transaction(doc, "Agent - Modify Grid") as trans:
        trans.Start()
        try:
            has_coords = all(k in tool_input for k in ["start_x", "start_y", "end_x", "end_y"])
            if has_coords:
                start_pt = XYZ(float(tool_input["start_x"]), float(tool_input["start_y"]), 0.0)
                end_pt = XYZ(float(tool_input["end_x"]), float(tool_input["end_y"]), 0.0)
                new_line = Line.CreateBound(start_pt, end_pt)
                
                was_pinned = grid.Pinned
                grid.Pinned = False
                grid.Curve = new_line
                grid.Pinned = was_pinned

            new_name = tool_input.get("name")
            if new_name and new_name != grid.Name:
                grid.Name = str(new_name)

            trans.Commit()
            return OrderedDict([
                ("status", "success"),
                ("message", "Grid '{}' successfully modified.".format(grid.Name)),
                ("data", OrderedDict([("element_id", grid.UniqueId)]))
            ])
        except Exception as ex:
            trans.RollBack()
            return {"status": "error", "message": "Failed to modify grid: " + str(ex)}


@registry.register(
    name="delete_grid",
    description="Deletes an existing gridline.",
    parameters={
        "type": "object",
        "properties": {
            "grid_id": {"type": "string", "description": "The UniqueId of the target grid."}
        },
        "required": ["grid_id"]
    }
)
def delete_grid(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import Transaction, Grid
    from collections import OrderedDict
    grid_id = tool_input["grid_id"]
    grid = doc.GetElement(grid_id)

    if not grid or not isinstance(grid, Grid):
        return {"status": "error", "message": "Grid element not found."}

    with Transaction(doc, "Agent - Delete Grid") as trans:
        trans.Start()
        try:
            grid.Pinned = False
            doc.Delete(grid.Id)
            trans.Commit()
            return OrderedDict([
                ("status", "success"),
                ("message", "Grid successfully deleted.")
            ])
        except Exception as ex:
            trans.RollBack()
            return {"status": "error", "message": "Failed to delete grid: " + str(ex)}


@registry.register(
    name="create_level",
    description="Creates a new horizontal datum level with options to configure custom visual extents.",
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
    from Autodesk.Revit.DB import Transaction, Level, FilteredElementCollector
    from collections import OrderedDict
    name = str(tool_input["name"])
    elevation = float(tool_input["elevation"])

    for lvl in FilteredElementCollector(doc).OfClass(Level):
        if lvl.Name.lower() == name.lower():
            return {"status": "error", "message": "Level name '{}' already exists.".format(name)}

    with Transaction(doc, "Agent - Create Level") as trans:
        trans.Start()
        try:
            new_level = Level.Create(doc, elevation)
            new_level.Name = name
            
            # Apply Default Extents Strategy
            maximize = tool_input.get("maximize_extents", True)
            if maximize:
                new_level.Maximize3DExtents()

            # Handle Extent copy from Reference Level
            ref_id = tool_input.get("reference_level_id")
            if ref_id:
                ref_level = doc.GetElement(ref_id)
                if ref_level and isinstance(ref_level, Level):
                    copy_level_extents(doc, ref_level, new_level)
            else:
                # Handle Explicit Coordinates if provided
                coords = ["min_x", "min_y", "max_x", "max_y"]
                if all(c in tool_input for c in coords):
                    apply_level_extents_to_views(
                        doc, 
                        new_level, 
                        float(tool_input["min_x"]), 
                        float(tool_input["min_y"]), 
                        float(tool_input["max_x"]), 
                        float(tool_input["max_y"])
                    )

            new_level.Pinned = True
            trans.Commit()
            return OrderedDict([
                ("status", "success"),
                ("message", "Level '{}' successfully created.".format(name)),
                ("data", OrderedDict([("element_id", new_level.UniqueId)]))
            ])
        except Exception as ex:
            trans.RollBack()
            return {"status": "error", "message": "Failed to create level: " + str(ex)}


@registry.register(
    name="modify_level",
    description="Modifies height elevation, renames, or updates the 3D/2D extents of an existing level.",
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
    from Autodesk.Revit.DB import Transaction, Level
    from collections import OrderedDict
    level_id = tool_input["level_id"]
    level = doc.GetElement(level_id)

    if not level or not isinstance(level, Level):
        return {"status": "error", "message": "Level element not found."}

    with Transaction(doc, "Agent - Modify Level") as trans:
        trans.Start()
        try:
            was_pinned = level.Pinned
            level.Pinned = False

            new_elev = tool_input.get("elevation")
            if new_elev is not None:
                level.Elevation = float(new_elev)

            new_name = tool_input.get("name")
            if new_name and new_name != level.Name:
                level.Name = str(new_name)

            # Apply updates to physical/visual extents
            maximize = tool_input.get("maximize_extents")
            if maximize:
                level.Maximize3DExtents()

            ref_id = tool_input.get("reference_level_id")
            if ref_id:
                ref_level = doc.GetElement(ref_id)
                if ref_level and isinstance(ref_level, Level):
                    copy_level_extents(doc, ref_level, level)
            else:
                coords = ["min_x", "min_y", "max_x", "max_y"]
                if any(c in tool_input for c in coords):
                    bbox = level.get_BoundingBox(None)
                    cur_min_x = bbox.Min.X if bbox else 0.0
                    cur_min_y = bbox.Min.Y if bbox else 0.0
                    cur_max_x = bbox.Max.X if bbox else 100.0
                    cur_max_y = bbox.Max.Y if bbox else 100.0
                    
                    new_min_x = float(tool_input.get("min_x", cur_min_x))
                    new_min_y = float(tool_input.get("min_y", cur_min_y))
                    new_max_x = float(tool_input.get("max_x", cur_max_x))
                    new_max_y = float(tool_input.get("max_y", cur_max_y))
                    
                    apply_level_extents_to_views(doc, level, new_min_x, new_min_y, new_max_x, new_max_y)

            level.Pinned = was_pinned
            trans.Commit()
            return OrderedDict([
                ("status", "success"),
                ("message", "Level '{}' successfully modified.".format(level.Name)),
                ("data", OrderedDict([("element_id", level.UniqueId)]))
            ])
        except Exception as ex:
            trans.RollBack()
            return {"status": "error", "message": "Failed to modify level: " + str(ex)}


@registry.register(
    name="delete_level",
    description="Deletes an existing level. Deletes all associated plan views automatically.",
    parameters={
        "type": "object",
        "properties": {
            "level_id": {"type": "string", "description": "The UniqueId of the target level."}
        },
        "required": ["level_id"]
    }
)
def delete_level(doc, ui_app, tool_input):
    from Autodesk.Revit.DB import Transaction, Level
    from collections import OrderedDict
    level_id = tool_input["level_id"]
    level = doc.GetElement(level_id)

    if not level or not isinstance(level, Level):
        return {"status": "error", "message": "Level element not found."}

    with Transaction(doc, "Agent - Delete Level") as trans:
        trans.Start()
        try:
            level.Pinned = False
            doc.Delete(level.Id)
            trans.Commit()
            return OrderedDict([
                ("status", "success"),
                ("message", "Level and its associated views successfully deleted.")
            ])
        except Exception as ex:
            trans.RollBack()
            return {"status": "error", "message": "Failed to delete level: " + str(ex)}
