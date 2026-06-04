# -*- coding: utf-8 -*-
import clr
import os
import sys

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import ExternalEvent

current_dir   = os.path.dirname(__file__)
dll_full_path = os.path.join(current_dir, "RevitAgentBridge.dll")
_LOG_PATH     = os.path.join(current_dir, "debug_tool_errors.log")
_MAX_LOG_SIZE = 2 * 1024 * 1024  # 2 MB rotation
_PORT         = 8080
_LOG_LEVEL    = "INFO"
_LOG_LEVEL_RANK = {"DEBUG": 0, "INFO": 1, "WARN": 2, "WARNING": 2, "ERROR": 3, "FATAL": 4}


if os.path.exists(dll_full_path):
    try:
        clr.AddReferenceToFileAndPath(dll_full_path)
    except Exception as e:
        print(">>> ERROR: Could not load RevitAgentBridge.dll: " + str(e))
        sys.exit()
else:
    print(">>> ERROR: RevitAgentBridge.dll not found in: " + current_dir)
    sys.exit()

from RevitAgentBridge import AgentExternalEventHandler, BridgeServer, BridgeRegistry


# =====================================================================
# DYNAMIC PYTHON EXECUTION ROUTER
#
# CRITICAL (IronPython GC rule): ALL registry state and tool wrappers
# MUST live inside this closure. IronPython garbage-collects module-level
# globals after the script finishes. Only the closure scope survives
# when C# calls PythonExecutor later.
# =====================================================================

def python_execution_router(*args):
    """
    Entry point called from C# on Revit's main thread.
    Supports:
        - python_execution_router(request_json_string) [Old DLL]
        - python_execution_router(ui_app, request_json_string) [New DLL]
    Parses the JSON payload, dispatches to the matching tool, returns JSON.
    """
    import json
    import time
    import os

    if len(args) == 2:
        ui_app, request_json_string = args
    else:
        ui_app = None
        request_json_string = args[0]

    # -----------------------------------------------------------------
    # IN-CLOSURE DEBUG LOG (GC-safe — local variables prevent GC issues)
    # -----------------------------------------------------------------
    def _log_debug(tool_name, message, level="INFO", _lp=_LOG_PATH, _lm=_MAX_LOG_SIZE):
        """Append a timestamped entry to the debug log file if severity >= _LOG_LEVEL."""
        try:
            req_rank = _LOG_LEVEL_RANK.get(level.upper(), 1)
            cfg_rank = _LOG_LEVEL_RANK.get(_LOG_LEVEL.upper(), 1)
            if req_rank < cfg_rank:
                return

            if os.path.exists(_lp) and os.path.getsize(_lp) > _lm:
                backup = _lp + ".old"
                if os.path.exists(backup):
                    os.remove(backup)
                os.rename(_lp, backup)
            with open(_lp, "a") as f:
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                f.write("[{}] [{:5s}] {}: {}\n".format(ts, level, tool_name, message))
        except Exception:
            pass  # Logging must never crash the tool

    # -----------------------------------------------------------------
    # IN-CLOSURE TOOL REGISTRY
    # Rebuilt on every call (fast dict/list ops), always consistent, GC-safe.
    # -----------------------------------------------------------------
    tool_registry  = []   # List of schema dicts — served via GET /tools/
    tool_functions = {}   # Maps tool name -> function pointer

    def register_tool(name, description, parameters, agent_instructions=""):
        """
        IronPython 2.7-compatible decorator factory.
        Stores the full schema (including agent_instructions) in tool_registry
        and the callable in tool_functions.
        """
        def decorator(fn):
            tool_registry.append({
                "name":               name,
                "description":        description,
                "agent_instructions": agent_instructions,
                "parameters":         parameters
            })
            tool_functions[name] = fn
            return fn
        return decorator

    # -----------------------------------------------------------------
    # PROJECT BASE POINT HELPER
    # -----------------------------------------------------------------
    def get_base_point_offset(doc):
        from Autodesk.Revit.DB import FilteredElementCollector, BasePoint, BuiltInParameter
        last_error = ""
        try:
            collector = FilteredElementCollector(doc).OfClass(BasePoint)
            for bp in collector:
                try:
                    if not bp.IsShared:
                        east  = bp.get_Parameter(BuiltInParameter.BASEPOINT_EASTWEST_PARAM).AsDouble()
                        north = bp.get_Parameter(BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM).AsDouble()
                        elev  = bp.get_Parameter(BuiltInParameter.BASEPOINT_ELEVATION_PARAM).AsDouble()
                        return east, north, elev, ""
                except Exception as e:
                    last_error = "Base point parameter read failed: {}".format(str(e))
                    continue
        except Exception as e:
            return 0.0, 0.0, 0.0, "Failed to collect base points: {}".format(str(e))
        if last_error:
            return 0.0, 0.0, 0.0, last_error
        return 0.0, 0.0, 0.0, "No non-shared base point found in project"

    # -----------------------------------------------------------------
    # UNIQUE NAME AND VIEW GENERATION HELPERS
    # -----------------------------------------------------------------
    def is_grid_name_unique(doc, name, exclude_id=None):
        from Autodesk.Revit.DB import FilteredElementCollector, Grid
        collector = FilteredElementCollector(doc).OfClass(Grid)
        for g in collector:
            if g.Name.lower() == name.lower():
                if exclude_id and g.UniqueId == exclude_id:
                    continue
                return False
        return True

    def is_level_name_unique(doc, name, exclude_id=None):
        from Autodesk.Revit.DB import FilteredElementCollector, Level
        collector = FilteredElementCollector(doc).OfClass(Level)
        for l in collector:
            if l.Name.lower() == name.lower():
                if exclude_id and l.UniqueId == exclude_id:
                    continue
                return False
        return True

    def get_view_family_type(doc, view_family):
        from Autodesk.Revit.DB import FilteredElementCollector, ViewFamilyType
        collector = FilteredElementCollector(doc).OfClass(ViewFamilyType)
        for vft in collector:
            if vft.ViewFamily == view_family:
                return vft
        return None

    def has_plan_view(doc, level_id, view_family):
        from Autodesk.Revit.DB import FilteredElementCollector, ViewPlan
        collector = FilteredElementCollector(doc).OfClass(ViewPlan)
        for vp in collector:
            if vp.GenLevel and vp.GenLevel.Id == level_id:
                vft = doc.GetElement(vp.GetTypeId())
                if vft and vft.ViewFamily == view_family:
                    return True
        return False

    def apply_datum_properties(doc, ui_app, datum, params, errors=None):
        from Autodesk.Revit.DB import BuiltInParameter, ElementId, DatumEnds, DatumExtentType
        from System.Collections.Generic import HashSet
        
        # 1. Scope Box
        if "scope_box_id" in params:
            sb_id_str = params["scope_box_id"]
            sb_param = datum.get_Parameter(BuiltInParameter.DATUM_VOLUME_OF_INTEREST)
            if sb_param and not sb_param.IsReadOnly:
                if sb_id_str:
                    sb_el = doc.GetElement(sb_id_str)
                    if sb_el:
                        sb_param.Set(sb_el.Id)
                else:
                    sb_param.Set(ElementId.InvalidElementId)
                    
        # 2. Maximize 3D Extents
        if params.get("maximize_3d_extents") is True:
            try:
                datum.Maximize3DExtents()
            except Exception as e:
                if errors is not None:
                    errors.append("Maximize3DExtents failed: {}".format(str(e)))
                
        # 3. View-specific controls
        target_view_id = params.get("target_view_id")
        target_view = None
        if target_view_id:
            target_view = doc.GetElement(target_view_id)
        if not target_view:
            try:
                if ui_app is not None:
                    target_view = ui_app.ActiveUIDocument.ActiveView
                else:
                    target_view = __revit__.ActiveUIDocument.ActiveView
            except Exception as e:
                if errors is not None:
                    errors.append("Could not get active view: {}".format(str(e)))
                
        if target_view:
            # Datum Extent Type (2D vs 3D)
            if "datum_extent_type" in params:
                det_str = params["datum_extent_type"]
                det = DatumExtentType.ViewSpecific if det_str == "2D" else DatumExtentType.Model
                try:
                    datum.SetDatumExtentType(DatumEnds.End0, target_view, det)
                    datum.SetDatumExtentType(DatumEnds.End1, target_view, det)
                except Exception as e:
                    if errors is not None:
                        errors.append("SetDatumExtentType failed: {}".format(str(e)))
            
            # Show/Hide Bubbles
            if "show_bubble_at_start" in params:
                if params["show_bubble_at_start"]:
                    datum.ShowBubbleInView(DatumEnds.End0, target_view)
                else:
                    datum.HideBubbleInView(DatumEnds.End0, target_view)
            if "show_bubble_at_end" in params:
                if params["show_bubble_at_end"]:
                    datum.ShowBubbleInView(DatumEnds.End1, target_view)
                else:
                    datum.HideBubbleInView(DatumEnds.End1, target_view)
                    
            # Start/End Offsets
            start_offset = params.get("start_offset")
            end_offset = params.get("end_offset")
            if start_offset is not None or end_offset is not None:
                start_offset = float(start_offset or 0.0)
                end_offset = float(end_offset or 0.0)
                
                try:
                    datum.SetDatumExtentType(DatumEnds.End0, target_view, DatumExtentType.ViewSpecific)
                    datum.SetDatumExtentType(DatumEnds.End1, target_view, DatumExtentType.ViewSpecific)
                    
                    view_curves = datum.GetCurvesInView(DatumExtentType.ViewSpecific, target_view)
                    if view_curves and len(view_curves) > 0:
                        v_curve = view_curves[0]
                        is_arc = v_curve.GetType().Name == "Arc"
                        if is_arc:
                            v_center = v_curve.Center
                            v_radius = v_curve.Radius
                            v_xAxis = v_curve.XDirection
                            v_yAxis = v_curve.YDirection
                            
                            def get_angle(pt, c, xDir, yDir):
                                vec = pt - c
                                x = vec.DotProduct(xDir)
                                y = vec.DotProduct(yDir)
                                import math
                                return math.atan2(y, x)
                                
                            v_start = v_curve.GetEndPoint(0)
                            v_end = v_curve.GetEndPoint(1)
                            
                            start_angle = get_angle(v_start, v_center, v_xAxis, v_yAxis)
                            end_angle = get_angle(v_end, v_center, v_xAxis, v_yAxis)
                            
                            new_start_angle = start_angle - start_offset / v_radius
                            new_end_angle = end_angle + end_offset / v_radius
                            
                            from Autodesk.Revit.DB import Arc
                            new_arc = Arc.Create(v_center, v_radius, new_start_angle, new_end_angle, v_xAxis, v_yAxis)
                            datum.SetCurveInView(DatumExtentType.ViewSpecific, target_view, new_arc)
                        else:
                            v_start = v_curve.GetEndPoint(0)
                            v_end = v_curve.GetEndPoint(1)
                            direction = (v_end - v_start).Normalize()
                            
                            new_start = v_start - direction * start_offset
                            new_end = v_end + direction * end_offset
                            
                            from Autodesk.Revit.DB import Line
                            new_line = Line.CreateBound(new_start, new_end)
                            datum.SetCurveInView(DatumExtentType.ViewSpecific, target_view, new_line)
                except Exception as e:
                    if errors is not None:
                        errors.append("Offset curve adjustment failed: {}".format(str(e)))
                    
            # Propagate to Views
            if "propagate_to_views" in params and params["propagate_to_views"]:
                try:
                    parallel_views_set = HashSet[ElementId]()
                    for view_id_str in params["propagate_to_views"]:
                        dest_view = doc.GetElement(view_id_str)
                        if dest_view:
                            parallel_views_set.Add(dest_view.Id)
                    if parallel_views_set.Count > 0:
                        datum.PropagateToViews(target_view, parallel_views_set)
                except Exception as e:
                    if errors is not None:
                        errors.append("PropagateToViews failed: {}".format(str(e)))

    # -----------------------------------------------------------------
    # SYSTEM TOOL: get_context (internal, not in registered list)
    # -----------------------------------------------------------------
    def tool_get_context(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Level, FamilySymbol
        pbp_x, pbp_y, pbp_z, pbp_err = get_base_point_offset(doc)
        levels_list   = []
        families_dict = {}
        errors = []
        if pbp_err:
            errors.append("Base point: " + pbp_err)

        level_collector = FilteredElementCollector(doc).OfClass(Level).ToElements()
        for lvl in level_collector:
            try:
                if lvl:
                    levels_list.append({
                        "name":      lvl.Name or "Unnamed Level",
                        "id":        lvl.UniqueId,
                        "elevation": lvl.Elevation - pbp_z
                    })
            except Exception as e:
                errors.append("Skipped level '{}': {}".format(getattr(lvl, 'Name', '?'), str(e)))

        symbol_collector = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
        for symbol in symbol_collector:
            try:
                if symbol:
                    fam_name = None
                    try:
                        fam_name = symbol.FamilyName
                    except Exception as e:
                        pass  # Try fallback
                    if not fam_name:
                        try:
                            fam_name = symbol.Family.Name
                        except Exception as e:
                            pass  # Try fallback
                    if not fam_name:
                        try:
                            fam_name = symbol.Category.Name
                        except Exception as e:
                            errors.append("Symbol has no family/category: {}".format(str(e)))

                    type_name = symbol.Name
                    if fam_name:
                        if fam_name not in families_dict:
                            families_dict[fam_name] = []
                        if type_name and type_name not in families_dict[fam_name]:
                            families_dict[fam_name].append(type_name)
            except Exception as e:
                errors.append("Skipped family symbol: {}".format(str(e)))

        result = {
            "status":         "success",
            "document_title": doc.Title or "Untitled",
            "levels":         levels_list,
            "families":       families_dict
        }
        if errors:
            result["warnings"] = errors
        return result

    # -----------------------------------------------------------------
    # FETCH TOOLS (Read-only context queries)
    # -----------------------------------------------------------------

    @register_tool(
        name="fetch_project_info",
        description=(
            "Fetches basic identification metadata about the active Revit "
            "project. Returns the document title and file path."
        ),
        agent_instructions=(
            "Call only when the document title or file path is explicitly "
            "needed. Do not call this before every action."
        ),
        parameters={
            "type":       "object",
            "properties": {},
            "required":   []
        }
    )
    def tool_fetch_project_info(doc, tool_input):
        file_path = ""
        file_path_error = ""
        try:
            if doc.PathName:
                file_path = doc.PathName
        except Exception as e:
            file_path_error = "Could not read file path: {}".format(str(e))

        result = {
            "status":         "success",
            "document_title": doc.Title or "Untitled",
            "file_path":      file_path
        }
        if file_path_error:
            result["warnings"] = [file_path_error]
        return result

    @register_tool(
        name="fetch_levels",
        description=(
            "Fetches all levels in the active Revit project. Returns each "
            "level's name, UniqueId, elevation in feet relative to the Project Base Point, "
            "3D curve extents (curve_start_x, curve_end_x — when available), "
            "associated Scope Box, structural metadata, level type, and view specific settings."
        ),
        agent_instructions=(
            "Call before any tool that requires a level_id. "
            "Use the returned 'id' (UniqueId) as-is for the level_id argument. "
            "If levels have curve_start_x and curve_end_x, use those for grid extents. "
            "If curve extents are not available, get extents from: "
            "(1) existing grids via fetch_grids, or (2) ask the user for building dimensions. "
            "IMPORTANT: If this tool returns 'status': 'error', STOP immediately and inform the user of the problem. "
            "Do NOT proceed with other tools until the issue is resolved."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target_view_id": {
                    "type": "string",
                    "description": "Optional UniqueId of a specific section/elevation view to query view-specific (2D) extents, offsets, and bubble visibilities."
                }
            },
            "required": []
        }
    )
    def tool_fetch_levels(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Level, DatumEnds, DatumExtentType, BuiltInParameter, ElementId, BoundingBoxXYZ, Outline
        pbp_x, pbp_y, pbp_z, pbp_err = get_base_point_offset(doc)
        errors = []
        if pbp_err:
            errors.append("Base point: " + pbp_err)
        
        target_view_id = tool_input.get("target_view_id")
        target_view = None
        if target_view_id:
            target_view = doc.GetElement(target_view_id)
        if not target_view:
            try:
                if ui_app is not None:
                    target_view = ui_app.ActiveUIDocument.ActiveView
                else:
                    target_view = __revit__.ActiveUIDocument.ActiveView
            except Exception as e:
                errors.append("Could not get active view: {}".format(str(e)))

        levels_list = []
        level_collector = FilteredElementCollector(doc).OfClass(Level).ToElements()
        for lvl in level_collector:
            try:
                if not lvl:
                    continue
                    
                lvl_data = {
                    "name": lvl.Name or "Unnamed Level",
                    "id": lvl.UniqueId,
                    "elevation": lvl.Elevation - pbp_z
                }
                
                # Level line extents — report the 3D curve start/end coordinates
                # ONLY include if we have real level curve data (not fabricated values).
                # If curves aren't available, the AI should get extents from:
                #   1. Existing grids (fetch_grids)
                #   2. User input
                curve_error = ""
                try:
                    from Autodesk.Revit.DB import ViewType, View
                    all_views = FilteredElementCollector(doc).OfClass(View).ToElements()
                    
                    x_coords = []
                    y_coords = []
                    
                    for v in all_views:
                        if not v or v.IsTemplate:
                            continue
                        if v.ViewType == ViewType.Elevation or v.ViewType == ViewType.Section:
                            try:
                                model_curves = lvl.GetCurvesInView(DatumExtentType.Model, v)
                                if model_curves:
                                    for curve in model_curves:
                                        ep0 = curve.GetEndPoint(0)
                                        ep1 = curve.GetEndPoint(1)
                                        x_coords.extend([ep0.X, ep1.X])
                                        y_coords.extend([ep0.Y, ep1.Y])
                            except Exception as e:
                                err_msg = str(e)
                                if "datum plane cannot be visible" not in err_msg.lower():
                                    _log_debug("fetch_levels", "GetCurvesInView for '{}' in '{}': {}".format(lvl.Name, v.Name, err_msg), level="DEBUG")
                                continue
                                
                    if x_coords and y_coords:
                        min_x = min(x_coords)
                        max_x = max(x_coords)
                        min_y = min(y_coords)
                        max_y = max(y_coords)
                        
                        lvl_data["curve_start_x"] = round(min_x - pbp_x, 2)
                        lvl_data["curve_start_y"] = round(min_y - pbp_y, 2)
                        lvl_data["curve_end_x"] = round(max_x - pbp_x, 2)
                        lvl_data["curve_end_y"] = round(max_y - pbp_y, 2)
                    else:
                        curve_error = "No level curves found across all elevation/section views."
                except Exception as e:
                    curve_error = "Curve extents for '{}': {}".format(lvl.Name, str(e))
                
                if "curve_start_x" not in lvl_data and curve_error:
                    errors.append(curve_error)
                elif "curve_start_x" not in lvl_data:
                    errors.append("No curve extents available for level '{}' (no valid view or empty curves). Use fetch_grids or ask user for extents.".format(lvl.Name))
                
                # Structural
                struct_param = lvl.get_Parameter(BuiltInParameter.LEVEL_IS_STRUCTURAL)
                lvl_data["is_structural"] = (struct_param.AsInteger() == 1) if struct_param else False
                
                # Scope Box
                sb_param = lvl.get_Parameter(BuiltInParameter.DATUM_VOLUME_OF_INTEREST)
                scope_box_id = ""
                if sb_param and sb_param.HasValue:
                    sb_id = sb_param.AsElementId()
                    if sb_id != ElementId.InvalidElementId:
                        sb_el = doc.GetElement(sb_id)
                        if sb_el:
                            scope_box_id = sb_el.UniqueId
                lvl_data["scope_box_id"] = scope_box_id
                
                # Level Type
                type_id = lvl.GetTypeId()
                type_el = doc.GetElement(type_id)
                lvl_data["level_type_id"] = type_el.UniqueId if type_el else ""
                
                # View specific details
                if target_view:
                    try:
                        ext_type = lvl.GetDatumExtentTypeInView(DatumEnds.End0, target_view)
                        lvl_data["datum_extent_type"] = "2D" if ext_type == DatumExtentType.ViewSpecific else "3D"
                        lvl_data["show_bubble_at_start"] = lvl.IsBubbleVisibleInView(DatumEnds.End0, target_view)
                        lvl_data["show_bubble_at_end"] = lvl.IsBubbleVisibleInView(DatumEnds.End1, target_view)
                        
                        view_curves = lvl.GetCurvesInView(DatumExtentType.ViewSpecific, target_view)
                        model_curves = lvl.GetCurvesInView(DatumExtentType.Model, target_view)
                        if view_curves and len(view_curves) > 0 and model_curves and len(model_curves) > 0:
                            v_curve = view_curves[0]
                            m_curve = model_curves[0]
                            v_start = v_curve.GetEndPoint(0)
                            v_end = v_curve.GetEndPoint(1)
                            m_start = m_curve.GetEndPoint(0)
                            m_end = m_curve.GetEndPoint(1)
                            direction = (m_end - m_start).Normalize()
                            lvl_data["start_offset"] = (m_start - v_start).DotProduct(direction)
                            lvl_data["end_offset"] = (v_end - m_end).DotProduct(direction)
                        else:
                            lvl_data["start_offset"] = 0.0
                            lvl_data["end_offset"] = 0.0
                    except Exception as e:
                        errors.append("View-specific details for '{}': {}".format(lvl.Name, str(e)))
                        lvl_data["datum_extent_type"] = "3D"
                        lvl_data["show_bubble_at_start"] = False
                        lvl_data["show_bubble_at_end"] = True
                        lvl_data["start_offset"] = 0.0
                        lvl_data["end_offset"] = 0.0
                else:
                    lvl_data["datum_extent_type"] = "3D"
                    lvl_data["show_bubble_at_start"] = False
                    lvl_data["show_bubble_at_end"] = True
                    lvl_data["start_offset"] = 0.0
                    lvl_data["end_offset"] = 0.0
                    
                levels_list.append(lvl_data)
            except Exception as e:
                errors.append("Skipped level '{}': {}".format(getattr(lvl, 'Name', '?'), str(e)))

        # If no levels were collected, this is a critical error - the AI cannot proceed
        if not levels_list:
            if not errors:
                errors.append("No levels found in the project. The project may be empty, corrupted, or not a valid Revit model.")
            return {
                "status": "error",
                "message": "Failed to fetch levels: " + errors[0],
                "errors": errors,
                "levels": [],
                "count": 0
            }
        
        result = {
            "status": "success",
            "levels": levels_list
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="fetch_grids",
        description=(
            "Fetches all existing reference gridlines in the active Revit project. "
            "Returns each grid's name, UniqueId, start/end coordinates in Revit's internal "
            "coordinate system (feet), geometric definition (linear or arc), scope box, "
            "type, and view specific settings."
        ),
        agent_instructions=(
            "Call before create_grid or modify_grid to check existing configurations. "
            "IMPORTANT: If this tool returns 'status': 'error', STOP and inform the user. "
            "Do NOT proceed with grid creation/modification until the error is resolved."
        ),
        parameters={
            "type": "object",
            "properties": {
                "target_view_id": {
                    "type": "string",
                    "description": "Optional UniqueId of a specific view to query view-specific (2D) extents, offsets, and bubble visibilities."
                }
            },
            "required": []
        }
    )
    def tool_fetch_grids(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Grid, DatumEnds, DatumExtentType, BuiltInParameter, ElementId, Arc, Line
        import math
        errors = []
        
        target_view_id = tool_input.get("target_view_id")
        target_view = None
        if target_view_id:
            target_view = doc.GetElement(target_view_id)
        if not target_view:
            try:
                if ui_app is not None:
                    target_view = ui_app.ActiveUIDocument.ActiveView
                else:
                    target_view = __revit__.ActiveUIDocument.ActiveView
            except Exception as e:
                errors.append("Could not get active view: {}".format(str(e)))

        grids_list = []
        grid_collector = FilteredElementCollector(doc).OfClass(Grid).ToElements()
        for grid in grid_collector:
            try:
                if not grid:
                    continue
                curve = grid.Curve
                if not curve:
                    continue
                    
                is_curved = isinstance(curve, Arc) or curve.GetType().Name == "Arc"
                start_pt = curve.GetEndPoint(0)
                end_pt = curve.GetEndPoint(1)
                
                # Report coordinates in Revit's internal coordinate system,
                # matching how create_grid places them (no PBP offset).
                grid_data = {
                    "name": grid.Name or "Unnamed Grid",
                    "id": grid.UniqueId,
                    "is_curved": is_curved,
                    "start_x": start_pt.X,
                    "start_y": start_pt.Y,
                    "start_z": start_pt.Z,
                    "end_x": end_pt.X,
                    "end_y": end_pt.Y,
                    "end_z": end_pt.Z
                }
                
                if is_curved:
                    center = curve.Center
                    radius = curve.Radius
                    xAxis = curve.XDirection
                    yAxis = curve.YDirection
                    mid_pt = curve.Evaluate(0.5, True)
                    
                    def get_angle(pt, c, xDir, yDir):
                        vec = pt - c
                        x = vec.DotProduct(xDir)
                        y = vec.DotProduct(yDir)
                        return math.atan2(y, x)
                        
                    start_angle = get_angle(start_pt, center, xAxis, yAxis)
                    end_angle = get_angle(end_pt, center, xAxis, yAxis)
                    
                    grid_data.update({
                        "arc_point_x": mid_pt.X,
                        "arc_point_y": mid_pt.Y,
                        "arc_point_z": mid_pt.Z,
                        "center_x": center.X,
                        "center_y": center.Y,
                        "radius": radius,
                        "start_angle": start_angle,
                        "end_angle": end_angle
                    })
                    
                # Scope Box
                sb_param = grid.get_Parameter(BuiltInParameter.DATUM_VOLUME_OF_INTEREST)
                scope_box_id = ""
                if sb_param and sb_param.HasValue:
                    sb_id = sb_param.AsElementId()
                    if sb_id != ElementId.InvalidElementId:
                        sb_el = doc.GetElement(sb_id)
                        if sb_el:
                            scope_box_id = sb_el.UniqueId
                grid_data["scope_box_id"] = scope_box_id
                
                # Grid Type
                type_id = grid.GetTypeId()
                type_el = doc.GetElement(type_id)
                grid_data["grid_type_id"] = type_el.UniqueId if type_el else ""
                
                # View specific details
                if target_view:
                    try:
                        ext_type = grid.GetDatumExtentTypeInView(DatumEnds.End0, target_view)
                        grid_data["datum_extent_type"] = "2D" if ext_type == DatumExtentType.ViewSpecific else "3D"
                        grid_data["show_bubble_at_start"] = grid.IsBubbleVisibleInView(DatumEnds.End0, target_view)
                        grid_data["show_bubble_at_end"] = grid.IsBubbleVisibleInView(DatumEnds.End1, target_view)
                        
                        view_curves = grid.GetCurvesInView(DatumExtentType.ViewSpecific, target_view)
                        if view_curves and len(view_curves) > 0:
                            v_curve = view_curves[0]
                            v_start = v_curve.GetEndPoint(0)
                            v_end = v_curve.GetEndPoint(1)
                            
                            if is_curved:
                                v_center = v_curve.Center
                                v_radius = v_curve.Radius
                                v_xAxis = v_curve.XDirection
                                v_yAxis = v_curve.YDirection
                                v_start_angle = get_angle(v_start, v_center, v_xAxis, v_yAxis)
                                v_end_angle = get_angle(v_end, v_center, v_xAxis, v_yAxis)
                                grid_data["start_offset"] = (start_angle - v_start_angle) * radius
                                grid_data["end_offset"] = (v_end_angle - end_angle) * radius
                            else:
                                direction = (end_pt - start_pt).Normalize()
                                grid_data["start_offset"] = (start_pt - v_start).DotProduct(direction)
                                grid_data["end_offset"] = (v_end - end_pt).DotProduct(direction)
                        else:
                            grid_data["start_offset"] = 0.0
                            grid_data["end_offset"] = 0.0
                    except Exception as e:
                        errors.append("View-specific details for grid '{}': {}".format(grid.Name, str(e)))
                        grid_data["datum_extent_type"] = "3D"
                        grid_data["show_bubble_at_start"] = False
                        grid_data["show_bubble_at_end"] = True
                        grid_data["start_offset"] = 0.0
                        grid_data["end_offset"] = 0.0
                else:
                    grid_data["datum_extent_type"] = "3D"
                    grid_data["show_bubble_at_start"] = False
                    grid_data["show_bubble_at_end"] = True
                    grid_data["start_offset"] = 0.0
                    grid_data["end_offset"] = 0.0
                    
                grids_list.append(grid_data)
            except Exception as e:
                errors.append("Skipped grid '{}': {}".format(getattr(grid, 'Name', '?'), str(e)))

        # If no grids were collected and we expected some, report error
        # Note: empty grids is valid for new projects, so only error if there were collection errors
        if not grids_list and errors:
            return {
                "status": "error",
                "message": "Failed to fetch grids: " + errors[0],
                "errors": errors,
                "coordinate_reference": "Internal (Revit)",
                "grids": [],
                "count": 0
            }
        
        result = {
            "status":               "success",
            "coordinate_reference": "Internal (Revit)",
            "grids":                grids_list
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="fetch_families",
        description=(
            "Fetches loaded family symbols (types) in the active Revit project. "
            "Returns a dictionary mapping family names to lists of their available type names. "
            "Optionally filters by category to reduce response size."
        ),
        agent_instructions=(
            "Call before place_family. "
            "Use the exact family_name and type_name strings as returned "
            "— do not approximate or guess names. "
            "If the required family is not in the list, inform the user it is "
            "not loaded in the project. "
            "IMPORTANT: Always specify a category_filter (e.g. 'Doors', 'Windows', 'Furniture') "
            "to avoid slow responses from large projects. "
            "If this tool returns 'status': 'error', STOP and inform the user. "
            "Do NOT attempt to place families until the error is resolved."
        ),
        parameters={
            "type":       "object",
            "properties": {
                "category_filter": {
                    "type": "string",
                    "description": "Optional category name to filter results (e.g. 'Doors', 'Windows', 'Furniture', 'Plumbing Fixtures'). Leave empty to fetch all categories (may be slow in large projects)."
                }
            },
            "required":   []
        }
    )
    def tool_fetch_families(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol, BuiltInCategory
        
        # Optional category filter for performance
        category_filter = tool_input.get("category_filter", "").strip()
        
        families_dict = {}
        seen_pairs = set()  # Fast deduplication using (family, type) tuples
        errors = []
        
        # Build collector - iterate directly without ToElements() for better performance
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        
        # Apply category filter if specified
        if category_filter:
            # Try to find matching category
            categories = doc.Settings.Categories
            target_cat = None
            for cat in categories:
                if cat.Name and cat.Name.lower() == category_filter.lower():
                    target_cat = cat
                    break
            
            if target_cat:
                collector = collector.OfCategoryId(target_cat.Id)
            # If category not found, return empty result with helpful message
            else:
                return {
                    "status": "success",
                    "families": {},
                    "message": "Category '{}' not found. Common categories: Doors, Windows, Furniture, Plumbing Fixtures, Lighting Fixtures, Mechanical Equipment.".format(category_filter)
                }
        
        # Iterate directly over collector (avoids creating full list in memory)
        for symbol in collector:
            try:
                if not symbol:
                    continue
                    
                # Get family name with fallbacks
                fam_name = None
                try:
                    fam_name = symbol.FamilyName
                except Exception as e:
                    pass  # Try fallback
                if not fam_name:
                    try:
                        fam_name = symbol.Family.Name
                    except Exception as e:
                        pass  # Try fallback
                if not fam_name:
                    try:
                        if symbol.Category:
                            fam_name = symbol.Category.Name
                    except Exception as e:
                        errors.append("Symbol has no family/category: {}".format(str(e)))

                type_name = symbol.Name
                if fam_name and type_name:
                    pair = (fam_name, type_name)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        if fam_name not in families_dict:
                            families_dict[fam_name] = []
                        families_dict[fam_name].append(type_name)
            except Exception as e:
                errors.append("Skipped family symbol: {}".format(str(e)))

        # If no families were collected, this is likely a problem
        if not families_dict:
            if not errors:
                errors.append("No family symbols found in the project. The project may be empty or the category filter '{}' returned no results.".format(category_filter or "(none)"))
            return {
                "status": "error",
                "message": "Failed to fetch families: " + errors[0],
                "errors": errors,
                "families": {},
                "count": 0
            }
        
        result = {
            "status":   "success",
            "families": families_dict
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="fetch_sheets",
        description=(
            "Fetches all existing drawing sheets in the active Revit project. "
            "Returns each sheet's number, name, and UniqueId."
        ),
        agent_instructions=(
            "Call before create_sheet. "
            "Confirm no sheet with the same sheet_number already exists. "
            "Observe the existing numbering convention from the results. "
            "If this tool returns 'status': 'error', STOP and inform the user. "
            "Do NOT attempt to create sheets until the error is resolved."
        ),
        parameters={
            "type":       "object",
            "properties": {},
            "required":   []
        }
    )
    def tool_fetch_sheets(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, ViewSheet
        sheets_list = []
        errors = []
        sheet_collector = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
        for sheet in sheet_collector:
            try:
                if sheet:
                    sheets_list.append({
                        "number": sheet.SheetNumber or "",
                        "name":   sheet.Name or "Unnamed Sheet",
                        "id":     sheet.UniqueId
                    })
            except Exception as e:
                errors.append("Skipped sheet '{}': {}".format(getattr(sheet, 'SheetNumber', '?'), str(e)))

        # Empty sheets list is valid for new projects, but report errors if any
        if not sheets_list and errors:
            return {
                "status": "error",
                "message": "Failed to fetch sheets: " + errors[0],
                "errors": errors,
                "sheets": [],
                "count": 0
            }
        
        result = {
            "status": "success",
            "sheets": sheets_list
        }
        if errors:
            result["warnings"] = errors
        return result

    # -----------------------------------------------------------------
    # ACTION TOOLS (Write operations)
    # -----------------------------------------------------------------

    @register_tool(
        name="place_family",
        description=(
            "Places a loaded family symbol instance at a specified coordinate "
            "on a given level in the active Revit project."
        ),
        agent_instructions=(
            "Before calling: "
            "(1) Call fetch_levels to get a valid level_id. "
            "(2) Call fetch_families to get the exact family_name and type_name. "
            "Coordinates x and y are relative to the Project Base Point in feet. "
            "Use z=0.0 for level-hosted families unless the user explicitly specifies otherwise.\n"
            "(3) NEVER assume the family type, location, or level — if the user has not specified them, "
            "ASK the user to provide these details before calling this tool."
        ),
        parameters={
            "type": "object",
            "properties": {
                "family_name": {
                    "type":        "string",
                    "description": "The exact name of the family (e.g. 'Single-Flush')."
                },
                "type_name": {
                    "type":        "string",
                    "description": "The exact type name within the family (e.g. '36\" x 84\"')."
                },
                "level_id": {
                    "type":        "string",
                    "description": "The UniqueId of the host level element (from fetch_levels)."
                },
                "x": {
                    "type":        "number",
                    "description": "X coordinate in feet, relative to the Project Base Point."
                },
                "y": {
                    "type":        "number",
                    "description": "Y coordinate in feet, relative to the Project Base Point."
                },
                "z": {
                    "type":        "number",
                    "description": "Z coordinate in feet, relative to the Project Base Point. Use 0.0 for level-hosted families."
                }
            },
            "required": ["family_name", "type_name", "level_id", "x", "y", "z"]
        }
    )
    def tool_place_family(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Level, FamilySymbol, Transaction, XYZ
        import Autodesk.Revit.DB.Structure

        family_name = tool_input.get("family_name")
        type_name   = tool_input.get("type_name")
        level_id    = tool_input.get("level_id")
        x = float(tool_input.get("x", 0.0))
        y = float(tool_input.get("y", 0.0))
        z = float(tool_input.get("z", 0.0))

        level_el = doc.GetElement(level_id)
        if not level_el or not isinstance(level_el, Level):
            return {
                "status":  "error",
                "message": "Invalid level_id '{}'. Call fetch_levels to get a valid UniqueId.".format(level_id)
            }

        target_symbol = None
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
        symbol_errors = []
        for s in collector:
            try:
                if s:
                    if (s.FamilyName.lower() == family_name.lower() and
                            s.Name.lower() == type_name.lower()):
                        target_symbol = s
                        break
            except Exception as e:
                symbol_errors.append(str(e))

        if not target_symbol:
            return {
                "status":  "error",
                "message": "Symbol '{} - {}' is not loaded. Call fetch_families to verify available names.".format(
                    family_name, type_name
                )
            }

        pbp_x, pbp_y, pbp_z, pbp_err = get_base_point_offset(doc)
        if pbp_err:
            pass  # Use default offsets, warning not critical for placement

        with Transaction(doc, "AI Agent - Place Family") as trans:
            trans.Start()
            if not target_symbol.IsActive:
                target_symbol.Activate()
                doc.Regenerate()
            point    = XYZ(x + pbp_x, y + pbp_y, z + pbp_z)
            instance = doc.Create.NewFamilyInstance(
                point, target_symbol, level_el,
                Autodesk.Revit.DB.Structure.StructuralType.NonStructural
            )
            trans.Commit()
            placed_id = instance.UniqueId

        return {
            "status":     "success",
            "message":    "Successfully placed '{} - {}' at PBP-relative ({}, {}, {}).".format(
                family_name, type_name, x, y, z
            ),
            "element_id": placed_id
        }

    @register_tool(
        name="create_grid",
        description=(
            "Creates a new reference gridline in the active Revit project. "
            "Supports linear geometry, curved (arc) geometry, physical extents, "
            "bubble visibility, and view specific offsets."
        ),
        agent_instructions=(
            "CRITICAL: Before using this tool, check the response from fetch_levels and fetch_grids. "
            "If either returns 'status': 'error', STOP and address the error FIRST. Do NOT proceed with grid creation.\n"
            "PLACEMENT CONTEXT — read this carefully before choosing coordinates:\n"
            "1. DETERMINE BUILDING EXTENTS from ONE of these sources (in priority order):\n"
            "   a) Level extents: call fetch_levels and check if levels have curve_start_x and curve_end_x\n"
            "   b) Existing grids: call fetch_grids and use the existing grid positions/spans\n"
            "   c) User input: if neither above is available, ASK the user for building dimensions\n"
            "2. ALWAYS call fetch_grids to check existing grids. If grids already exist, place new ones ADJACENT to them "
            "(continue the spacing pattern). Do NOT overlap or place arbitrarily.\n"
            "3. If the user specifies spacing (e.g. '10 meters apart'), convert to feet (1m = 3.28084ft) and apply consistently.\n"
            "4. If you lack enough information (no level extents, no existing grids, user hasn't specified dimensions), "
            "ASK the user for clarification before placing. Do NOT guess or use arbitrary values.\n"
            "5. GRID ORIENTATION — critical for crossing grids:\n"
            "   - Vertical grids: constant X position, spanning Y across the building width\n"
            "   - Horizontal grids: constant Y position, spanning X across the building length\n"
            "   - ALL grids MUST intersect each other to form a proper grid network\n"
            "COORDINATES: All in Revit's internal coordinate system (feet). "
            "Specify either linear (start_x, start_y, end_x, end_y) OR "
            "curved (start_x, start_y, end_x, end_y, arc_point_x, arc_point_y OR "
            "center_x, center_y, radius, start_angle, end_angle)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique display name of the grid (e.g. 'A', '1')."
                },
                "start_x": {
                    "type": "number",
                    "description": "Starting X coordinate in feet, in Revit's internal coordinate system."
                },
                "start_y": {
                    "type": "number",
                    "description": "Starting Y coordinate in feet, in Revit's internal coordinate system."
                },
                "start_z": {
                    "type": "number",
                    "description": "Starting Z coordinate in feet, in Revit's internal coordinate system. Defaults to 0."
                },
                "end_x": {
                    "type": "number",
                    "description": "Ending X coordinate in feet, in Revit's internal coordinate system."
                },
                "end_y": {
                    "type": "number",
                    "description": "Ending Y coordinate in feet, in Revit's internal coordinate system."
                },
                "end_z": {
                    "type": "number",
                    "description": "Ending Z coordinate in feet, in Revit's internal coordinate system. Defaults to 0."
                },
                "arc_point_x": {
                    "type": "number",
                    "description": "X coordinate of a third point along the arc in Revit's internal coordinate system (feet)."
                },
                "arc_point_y": {
                    "type": "number",
                    "description": "Y coordinate of a third point along the arc in Revit's internal coordinate system (feet)."
                },
                "arc_point_z": {
                    "type": "number",
                    "description": "Z coordinate of a third point along the arc in Revit's internal coordinate system (feet)."
                },
                "center_x": {
                    "type": "number",
                    "description": "Center point X coordinate for radial arcs in Revit's internal coordinate system (feet)."
                },
                "center_y": {
                    "type": "number",
                    "description": "Center point Y coordinate for radial arcs in Revit's internal coordinate system (feet)."
                },
                "radius": {
                    "type": "number",
                    "description": "Radius distance of the curved arc (feet)."
                },
                "start_angle": {
                    "type": "number",
                    "description": "Starting angle of the arc (radians)."
                },
                "end_angle": {
                    "type": "number",
                    "description": "Ending angle of the arc (radians)."
                },
                "scope_box_id": {
                    "type": "string",
                    "description": "The UniqueId of an existing Scope Box to control the grid's 3D boundary."
                },
                "maximize_3d_extents": {
                    "type": "boolean",
                    "description": "Forces the grid's 3D plane to automatically expand to encompass all model geometry."
                },
                "datum_extent_type": {
                    "type": "string",
                    "description": "Options are '2D' (view-specific) or '3D' (model-wide) when making graphic adjustments."
                },
                "target_view_id": {
                    "type": "string",
                    "description": "The UniqueId of the view where view-specific (2D) adjustments are applied."
                },
                "start_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the start point of the grid line in a target view."
                },
                "end_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the end point of the grid line in a target view."
                },
                "propagate_to_views": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "A list of target view UniqueIds that should copy the same 2D grid line endpoints."
                },
                "grid_type_id": {
                    "type": "string",
                    "description": "The UniqueId of the Grid Type family symbol to control line patterns and bubble styles."
                },
                "show_bubble_at_start": {
                    "type": "boolean",
                    "description": "Shows the grid bubble at the starting coordinate (defaults to False)."
                },
                "show_bubble_at_end": {
                    "type": "boolean",
                    "description": "Shows the grid bubble at the ending coordinate (defaults to True)."
                }
            },
            "required": ["name"]
        }
    )
    def tool_create_grid(doc, tool_input):
        from Autodesk.Revit.DB import Transaction, XYZ, Line, Arc, Grid
        grid_name = tool_input.get("name")
        errors = []
        
        if not is_grid_name_unique(doc, grid_name):
            return {
                "status": "error",
                "message": "Grid name '{}' is already in use in the active project.".format(grid_name)
            }
        
        # Coordinates are used directly in Revit's internal coordinate system,
        # matching how manual grid drawing works. No PBP offset applied.
        start_x = float(tool_input.get("start_x", 0.0))
        start_y = float(tool_input.get("start_y", 0.0))
        start_z = float(tool_input.get("start_z", 0.0))
        end_x = float(tool_input.get("end_x", 0.0))
        end_y = float(tool_input.get("end_y", 0.0))
        end_z = float(tool_input.get("end_z", 0.0))
        
        try:
            if "arc_point_x" in tool_input:
                arc_x = float(tool_input["arc_point_x"])
                arc_y = float(tool_input.get("arc_point_y", 0.0))
                arc_z = float(tool_input.get("arc_point_z", 0.0))
                start_pt = XYZ(start_x, start_y, start_z)
                end_pt = XYZ(end_x, end_y, end_z)
                arc_pt = XYZ(arc_x, arc_y, arc_z)
                grid_curve = Arc.Create(start_pt, end_pt, arc_pt)
            elif "center_x" in tool_input:
                center_x = float(tool_input["center_x"])
                center_y = float(tool_input.get("center_y", 0.0))
                radius = float(tool_input.get("radius", 1.0))
                start_angle = float(tool_input.get("start_angle", 0.0))
                end_angle = float(tool_input.get("end_angle", 1.0))
                center_pt = XYZ(center_x, center_y, start_z)
                grid_curve = Arc.Create(center_pt, radius, start_angle, end_angle, XYZ(1,0,0), XYZ(0,1,0))
            else:
                start_pt = XYZ(start_x, start_y, start_z)
                end_pt = XYZ(end_x, end_y, end_z)
                grid_curve = Line.CreateBound(start_pt, end_pt)
        except Exception as e:
            return {
                "status": "error",
                "message": "Failed to create grid curve geometry: {}".format(str(e))
            }
            
        with Transaction(doc, "AI Agent - Create Grid") as trans:
            trans.Start()
            try:
                new_grid = Grid.Create(doc, grid_curve)
                new_grid.Name = grid_name
                
                # Expand the grid's 3D plane to encompass all model geometry.
                # This is critical for visibility — without it, the grid's 3D
                # extents are minimal and it won't appear in most views.
                # Revit's UI does this automatically when drawing manually.
                try:
                    new_grid.Maximize3DExtents()
                except Exception as e:
                    errors.append("Maximize3DExtents failed: {}".format(str(e)))
                
                # Grid Type
                if "grid_type_id" in tool_input:
                    type_el = doc.GetElement(tool_input["grid_type_id"])
                    if type_el:
                        new_grid.ChangeTypeId(type_el.Id)
                        
                # Apply other properties
                apply_datum_properties(doc, ui_app, new_grid, tool_input, errors)
                
                # Pin the grid to prevent accidental deletion
                new_grid.Pinned = True
                
                trans.Commit()
                grid_id = new_grid.UniqueId
            except Exception as ex:
                trans.RollBack()
                return {
                    "status": "error",
                    "message": "Failed to execute Grid.Create: {}".format(str(ex))
                }
                
        result = {
            "status":     "success",
            "message":    "Successfully created Grid '{}'.".format(grid_name),
            "element_id": grid_id
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="modify_grid",
        description=(
            "Modifies an existing reference gridline in the active Revit project. "
            "Supports modifying name, curve geometry (linear or arc), scope box, "
            "extent type, bubble visibility, offsets, and propagation."
        ),
        agent_instructions=(
            "Before calling: "
            "(1) Call fetch_grids to get the valid UniqueId for the grid_id parameter. "
            "IMPORTANT: This tool fully handles geometry changes in-place. "
            "NEVER use delete_grid + create_grid as a workaround to modify a grid. "
            "Always use this tool for any grid modification (position, name, extents, etc.)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "grid_id": {
                    "type": "string",
                    "description": "The UniqueId of the Grid to modify."
                },
                "name": {
                    "type": "string",
                    "description": "New display name of the grid. Must be unique."
                },
                "start_x": {
                    "type": "number",
                    "description": "Starting X coordinate in feet, in Revit's internal coordinate system."
                },
                "start_y": {
                    "type": "number",
                    "description": "Starting Y coordinate in feet, in Revit's internal coordinate system."
                },
                "start_z": {
                    "type": "number",
                    "description": "Starting Z coordinate in feet, in Revit's internal coordinate system."
                },
                "end_x": {
                    "type": "number",
                    "description": "Ending X coordinate in feet, in Revit's internal coordinate system."
                },
                "end_y": {
                    "type": "number",
                    "description": "Ending Y coordinate in feet, in Revit's internal coordinate system."
                },
                "end_z": {
                    "type": "number",
                    "description": "Ending Z coordinate in feet, in Revit's internal coordinate system."
                },
                "arc_point_x": {
                    "type": "number",
                    "description": "X coordinate of a third point along the arc in Revit's internal coordinate system (feet)."
                },
                "arc_point_y": {
                    "type": "number",
                    "description": "Y coordinate of a third point along the arc in Revit's internal coordinate system (feet)."
                },
                "arc_point_z": {
                    "type": "number",
                    "description": "Z coordinate of a third point along the arc in Revit's internal coordinate system (feet)."
                },
                "center_x": {
                    "type": "number",
                    "description": "Center point X coordinate for radial arcs in Revit's internal coordinate system (feet)."
                },
                "center_y": {
                    "type": "number",
                    "description": "Center point Y coordinate for radial arcs in Revit's internal coordinate system (feet)."
                },
                "radius": {
                    "type": "number",
                    "description": "Radius distance of the curved arc (feet)."
                },
                "start_angle": {
                    "type": "number",
                    "description": "Starting angle of the arc (radians)."
                },
                "end_angle": {
                    "type": "number",
                    "description": "Ending angle of the arc (radians)."
                },
                "scope_box_id": {
                    "type": "string",
                    "description": "The UniqueId of an existing Scope Box to control the grid's 3D boundary."
                },
                "maximize_3d_extents": {
                    "type": "boolean",
                    "description": "Forces the grid's 3D plane to automatically expand to encompass all model geometry."
                },
                "datum_extent_type": {
                    "type": "string",
                    "description": "Options are '2D' (view-specific) or '3D' (model-wide) when making graphic adjustments."
                },
                "target_view_id": {
                    "type": "string",
                    "description": "The UniqueId of the view where view-specific (2D) adjustments are applied."
                },
                "start_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the start point of the grid line in a target view."
                },
                "end_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the end point of the grid line in a target view."
                },
                "propagate_to_views": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "A list of target view UniqueIds that should copy the same 2D grid line endpoints."
                },
                "grid_type_id": {
                    "type": "string",
                    "description": "The UniqueId of the Grid Type family symbol to control line patterns and bubble styles."
                },
                "show_bubble_at_start": {
                    "type": "boolean",
                    "description": "Shows the grid bubble at the starting coordinate."
                },
                "show_bubble_at_end": {
                    "type": "boolean",
                    "description": "Shows the grid bubble at the ending coordinate."
                }
            },
            "required": ["grid_id"]
        }
    )
    def tool_modify_grid(doc, tool_input):
        from Autodesk.Revit.DB import (
            Transaction, XYZ, Line, Arc, Grid, BuiltInParameter, ElementId,
            DatumExtentType, DatumEnds, ElementTransformUtils
        )
        grid_id = tool_input["grid_id"]

        grid = doc.GetElement(grid_id)
        if not grid or not isinstance(grid, Grid):
            return {
                "status": "error",
                "message": "Grid element with UniqueId '{}' not found.".format(grid_id)
            }

        new_name = tool_input.get("name")
        if new_name and new_name != grid.Name:
            if not is_grid_name_unique(doc, new_name, exclude_id=grid.UniqueId):
                return {
                    "status": "error",
                    "message": "Grid name '{}' is already in use in the active project.".format(new_name)
                }

        target_view_id = tool_input.get("target_view_id")
        target_view = None
        if target_view_id:
            target_view = doc.GetElement(target_view_id)
        if not target_view:
            try:
                if ui_app is not None:
                    target_view = ui_app.ActiveUIDocument.ActiveView
                else:
                    target_view = __revit__.ActiveUIDocument.ActiveView
            except Exception as e:
                pass  # target_view stays None, datum properties that need a view will report error

        geo_params = ["start_x", "start_y", "end_x", "end_y", "arc_point_x", "center_x"]
        has_geo = any(p in tool_input for p in geo_params)
        errors = []

        with Transaction(doc, "AI Agent - Modify Grid") as trans:
            trans.Start()
            try:
                if has_geo:
                    old_curve = grid.Curve
                    old_is_arc = isinstance(old_curve, Arc) or old_curve.GetType().Name == "Arc"
                    old_start = old_curve.GetEndPoint(0)
                    old_end = old_curve.GetEndPoint(1)

                    # Coordinates in Revit's internal system (no PBP offset)
                    start_x = float(tool_input.get("start_x", old_start.X))
                    start_y = float(tool_input.get("start_y", old_start.Y))
                    start_z = float(tool_input.get("start_z", old_start.Z))
                    end_x = float(tool_input.get("end_x", old_end.X))
                    end_y = float(tool_input.get("end_y", old_end.Y))
                    end_z = float(tool_input.get("end_z", old_end.Z))

                    try:
                        if "arc_point_x" in tool_input or (old_is_arc and "center_x" not in tool_input):
                            if old_is_arc:
                                old_mid = old_curve.Evaluate(0.5, True)
                                def_arc_x = old_mid.X
                                def_arc_y = old_mid.Y
                                def_arc_z = old_mid.Z
                            else:
                                def_arc_x = 0.0
                                def_arc_y = 0.0
                                def_arc_z = 0.0

                            arc_x = float(tool_input.get("arc_point_x", def_arc_x))
                            arc_y = float(tool_input.get("arc_point_y", def_arc_y))
                            arc_z = float(tool_input.get("arc_point_z", def_arc_z))
                            start_pt = XYZ(start_x, start_y, start_z)
                            end_pt = XYZ(end_x, end_y, end_z)
                            arc_pt = XYZ(arc_x, arc_y, arc_z)
                            new_curve = Arc.Create(start_pt, end_pt, arc_pt)
                        elif "center_x" in tool_input:
                            center_x = float(tool_input["center_x"])
                            center_y = float(tool_input.get("center_y", 0.0))
                            radius = float(tool_input.get("radius", 1.0))
                            start_angle = float(tool_input.get("start_angle", 0.0))
                            end_angle = float(tool_input.get("end_angle", 1.0))
                            center_pt = XYZ(center_x, center_y, start_z)
                            new_curve = Arc.Create(center_pt, radius, start_angle, end_angle, XYZ(1,0,0), XYZ(0,1,0))
                        else:
                            start_pt = XYZ(start_x, start_y, start_z)
                            end_pt = XYZ(end_x, end_y, end_z)
                            new_curve = Line.CreateBound(start_pt, end_pt)
                    except Exception as ge:
                        trans.RollBack()
                        return {
                            "status": "error",
                            "message": "Failed to construct new grid curve: {}".format(str(ge))
                        }

                    # Unpin grid if pinned — pinned grids reject curve modifications
                    was_pinned = grid.Pinned
                    if was_pinned:
                        try:
                            grid.Pinned = False
                        except Exception as e:
                            errors.append("Failed to unpin grid: {}".format(str(e)))

                    # Strategy 1: direct curve assignment via LocationCurve (preserves element ID)
                    success_inplace = False
                    try:
                        loc = grid.Location
                        if loc and hasattr(loc, "Curve"):
                            loc.Curve = new_curve
                            success_inplace = True
                    except Exception as e:
                        errors.append("Strategy 1 (LocationCurve) failed: {}".format(str(e)))

                    # Strategy 2: transform-based move (works for parallel translation, preserves element ID)
                    if not success_inplace:
                        try:
                            old_mid = old_curve.Evaluate(0.5, True)
                            new_mid = new_curve.Evaluate(0.5, True)
                            delta = new_mid - old_mid
                            if not delta.IsZeroLength():
                                ElementTransformUtils.MoveElement(doc, grid.Id, delta)
                                success_inplace = True
                        except Exception as e:
                            errors.append("Strategy 2 (MoveElement) failed: {}".format(str(e)))

                    # Re-pin if it was originally pinned and we succeeded in-place
                    if success_inplace and was_pinned:
                        try:
                            grid.Pinned = True
                        except Exception as e:
                            errors.append("Failed to re-pin grid: {}".format(str(e)))

                    if success_inplace:
                        if new_name:
                            grid.Name = new_name
                    else:
                        # Strategy 3 (last resort): delete old grid and recreate with new geometry
                        final_name = new_name or grid.Name
                        type_id = grid.GetTypeId()
                        sb_param = grid.get_Parameter(BuiltInParameter.DATUM_VOLUME_OF_INTEREST)
                        old_sb_id = sb_param.AsElementId() if (sb_param and sb_param.HasValue) else ElementId.InvalidElementId

                        # Temporarily rename to free the name slot for the new element
                        grid.Name = grid.Name + "__tmp"
                        new_grid = Grid.Create(doc, new_curve)
                        new_grid.Name = final_name
                        new_grid.ChangeTypeId(type_id)

                        if old_sb_id != ElementId.InvalidElementId:
                            new_sb_param = new_grid.get_Parameter(BuiltInParameter.DATUM_VOLUME_OF_INTEREST)
                            if new_sb_param and not new_sb_param.IsReadOnly:
                                new_sb_param.Set(old_sb_id)

                        doc.Delete(grid.Id)
                        grid = new_grid
                else:
                    if new_name:
                        grid.Name = new_name

                if "grid_type_id" in tool_input:
                    type_el = doc.GetElement(tool_input["grid_type_id"])
                    if type_el:
                        grid.ChangeTypeId(type_el.Id)

                apply_datum_properties(doc, ui_app, grid, tool_input, errors)
                trans.Commit()
                grid_id = grid.UniqueId
            except Exception as ex:
                trans.RollBack()
                return {
                    "status": "error",
                    "message": "Failed to modify Grid: {}".format(str(ex))
                }

        result = {
            "status": "success",
            "message": "Successfully modified Grid '{}'.".format(new_name or grid.Name),
            "element_id": grid_id
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="delete_grid",
        description=(
            "Deletes an existing reference gridline from the active Revit project by its UniqueId."
        ),
        agent_instructions=(
            "Before calling: Call fetch_grids to get the valid UniqueId for the grid_id parameter. "
            "Confirm with the user before deleting grids, as this action cannot be undone."
        ),
        parameters={
            "type": "object",
            "properties": {
                "grid_id": {
                    "type": "string",
                    "description": "The UniqueId of the Grid to delete (from fetch_grids)."
                }
            },
            "required": ["grid_id"]
        }
    )
    def tool_delete_grid(doc, tool_input):
        from Autodesk.Revit.DB import Transaction, Grid
        grid_id = tool_input["grid_id"]
        
        grid = doc.GetElement(grid_id)
        if not grid or not isinstance(grid, Grid):
            return {
                "status": "error",
                "message": "Grid element with UniqueId '{}' not found.".format(grid_id)
            }
        
        grid_name = grid.Name or "Unnamed Grid"
        
        with Transaction(doc, "AI Agent - Delete Grid") as trans:
            trans.Start()
            try:
                # Unpin the grid before deleting
                if grid.Pinned:
                    grid.Pinned = False
                doc.Delete(grid.Id)
                trans.Commit()
            except Exception as ex:
                trans.RollBack()
                return {
                    "status": "error",
                    "message": "Failed to delete Grid '{}': {}".format(grid_name, str(ex))
                }
        
        return {
            "status": "success",
            "message": "Successfully deleted Grid '{}'.".format(grid_name)
        }

    @register_tool(
        name="create_level",
        description=(
            "Creates a new horizontal level in the active Revit project. "
            "Optionally creates plan views (Floor Plan, Ceiling Plan, Structural Plan) "
            "and applies a view template."
        ),
        agent_instructions=(
            "Before calling: "
            "(1) Call fetch_levels to verify the name is unique and check current elevations. "
            "Elevation is in feet relative to the Project Base Point.\n"
            "(2) NEVER assume the name or elevation — if the user has not specified them explicitly, "
            "ASK the user for the exact level name and elevation before calling this tool."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Unique display name of the level (e.g. '01 - FIRST FLOOR')."
                },
                "elevation": {
                    "type": "number",
                    "description": "The height of the level in feet, relative to the Project Base Point."
                },
                "scope_box_id": {
                    "type": "string",
                    "description": "The UniqueId of an existing Scope Box to control the level's 3D boundary."
                },
                "maximize_3d_extents": {
                    "type": "boolean",
                    "description": "Forces the level's 3D plane to automatically expand to encompass all model geometry."
                },
                "datum_extent_type": {
                    "type": "string",
                    "description": "Options are '2D' (view-specific) or '3D' (model-wide) when making graphic adjustments."
                },
                "target_view_id": {
                    "type": "string",
                    "description": "The UniqueId of the elevation/section view where view-specific (2D) adjustments are applied."
                },
                "start_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the start point of the level line in a target view."
                },
                "end_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the end point of the level line in a target view."
                },
                "propagate_to_views": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "A list of target Elevation/Section view UniqueIds that should copy the same 2D level line endpoints."
                },
                "level_type_id": {
                    "type": "string",
                    "description": "The UniqueId of the Level Type family symbol (determines line styles and head graphics)."
                },
                "show_bubble_at_start": {
                    "type": "boolean",
                    "description": "Shows the level bubble head at the starting end of the line (defaults to False)."
                },
                "show_bubble_at_end": {
                    "type": "boolean",
                    "description": "Shows the level bubble head at the ending end of the line (defaults to True)."
                },
                "is_structural": {
                    "type": "boolean",
                    "description": "Designates the level as a structural datum for analytical models."
                },
                "create_floor_plan": {
                    "type": "boolean",
                    "description": "Automatically creates an associated Floor Plan view (defaults to True)."
                },
                "create_ceiling_plan": {
                    "type": "boolean",
                    "description": "Automatically creates an associated Reflected Ceiling Plan (RCP) view (defaults to False)."
                },
                "create_structural_plan": {
                    "type": "boolean",
                    "description": "Automatically creates an associated Structural Plan view (defaults to False)."
                },
                "view_template_id": {
                    "type": "string",
                    "description": "The UniqueId of an existing View Template to apply to the newly generated views."
                }
            },
            "required": ["name", "elevation"]
        }
    )
    def tool_create_level(doc, tool_input):
        from Autodesk.Revit.DB import Transaction, Level, BuiltInParameter, ViewPlan, ViewFamily
        level_name = tool_input.get("name")
        elevation = float(tool_input.get("elevation", 0.0))
        errors = []
        
        if not is_level_name_unique(doc, level_name):
            return {
                "status": "error",
                "message": "Level name '{}' is already in use in the active project.".format(level_name)
            }
            
        pbp_x, pbp_y, pbp_z, pbp_err = get_base_point_offset(doc)
        if pbp_err:
            errors.append("Base point: " + pbp_err)
        absolute_elevation = elevation + pbp_z
        
        create_floor = tool_input.get("create_floor_plan", True)
        create_rcp = tool_input.get("create_ceiling_plan", False)
        create_struct = tool_input.get("create_structural_plan", False)
        view_temp_id = tool_input.get("view_template_id")
        
        with Transaction(doc, "AI Agent - Create Level") as trans:
            trans.Start()
            try:
                new_level = Level.Create(doc, absolute_elevation)
                new_level.Name = level_name
                
                # Structural
                is_struct = tool_input.get("is_structural", False)
                struct_param = new_level.get_Parameter(BuiltInParameter.LEVEL_IS_STRUCTURAL)
                if struct_param and not struct_param.IsReadOnly:
                    struct_param.Set(1 if is_struct else 0)
                    
                # Level Type
                if "level_type_id" in tool_input:
                    type_el = doc.GetElement(tool_input["level_type_id"])
                    if type_el:
                        new_level.ChangeTypeId(type_el.Id)
                        
                apply_datum_properties(doc, ui_app, new_level, tool_input, errors)
                
                # Generate associated views
                views_created = []
                if create_floor:
                    vft = get_view_family_type(doc, ViewFamily.FloorPlan)
                    if vft:
                        vp = ViewPlan.Create(doc, vft.Id, new_level.Id)
                        if view_temp_id:
                            vt = doc.GetElement(view_temp_id)
                            if vt:
                                vp.ViewTemplateId = vt.Id
                        views_created.append("Floor Plan: " + vp.Name)
                if create_rcp:
                    vft = get_view_family_type(doc, ViewFamily.CeilingPlan)
                    if vft:
                        vp = ViewPlan.Create(doc, vft.Id, new_level.Id)
                        if view_temp_id:
                            vt = doc.GetElement(view_temp_id)
                            if vt:
                                vp.ViewTemplateId = vt.Id
                        views_created.append("RCP: " + vp.Name)
                if create_struct:
                    vft = get_view_family_type(doc, ViewFamily.StructuralPlan)
                    if vft:
                        vp = ViewPlan.Create(doc, vft.Id, new_level.Id)
                        if view_temp_id:
                            vt = doc.GetElement(view_temp_id)
                            if vt:
                                vp.ViewTemplateId = vt.Id
                        views_created.append("Structural Plan: " + vp.Name)
                
                # Pin the level to prevent accidental deletion
                new_level.Pinned = True
                        
                trans.Commit()
                level_id = new_level.UniqueId
            except Exception as ex:
                trans.RollBack()
                return {
                    "status": "error",
                    "message": "Failed to create Level: {}".format(str(ex))
                }
                
        msg = "Successfully created Level '{}'.".format(level_name)
        if views_created:
            msg += " Generated views: {}.".format(", ".join(views_created))
            
        result = {
            "status": "success",
            "message": msg,
            "element_id": level_id
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="modify_level",
        description=(
            "Modifies an existing horizontal level in the active Revit project. "
            "Optionally creates plan views (Floor Plan, RCP, Structural Plan) "
            "and applies a view template."
        ),
        agent_instructions=(
            "Before calling: "
            "(1) Call fetch_levels to get the valid UniqueId for the level_id parameter."
        ),
        parameters={
            "type": "object",
            "properties": {
                "level_id": {
                    "type": "string",
                    "description": "The UniqueId of the Level to modify."
                },
                "name": {
                    "type": "string",
                    "description": "New display name of the level. Must be unique."
                },
                "elevation": {
                    "type": "number",
                    "description": "New height of the level in feet, relative to the Project Base Point."
                },
                "scope_box_id": {
                    "type": "string",
                    "description": "The UniqueId of an existing Scope Box to control the level's 3D boundary."
                },
                "maximize_3d_extents": {
                    "type": "boolean",
                    "description": "Forces the level's 3D plane to automatically expand to encompass all model geometry."
                },
                "datum_extent_type": {
                    "type": "string",
                    "description": "Options are '2D' (view-specific) or '3D' (model-wide) when making graphic adjustments."
                },
                "target_view_id": {
                    "type": "string",
                    "description": "The UniqueId of the elevation/section view where view-specific (2D) adjustments are applied."
                },
                "start_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the start point of the level line in a target view."
                },
                "end_offset": {
                    "type": "number",
                    "description": "The coordinate offset distance (feet) to extend or retract the end point of the level line in a target view."
                },
                "propagate_to_views": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "A list of target Elevation/Section view UniqueIds that should copy the same 2D level line endpoints."
                },
                "level_type_id": {
                    "type": "string",
                    "description": "The UniqueId of the Level Type family symbol."
                },
                "show_bubble_at_start": {
                    "type": "boolean",
                    "description": "Shows the level bubble head at the starting end."
                },
                "show_bubble_at_end": {
                    "type": "boolean",
                    "description": "Shows the level bubble head at the ending end."
                },
                "is_structural": {
                    "type": "boolean",
                    "description": "Designates the level as a structural datum for analytical models."
                },
                "create_floor_plan": {
                    "type": "boolean",
                    "description": "Creates associated Floor Plan if it does not already exist."
                },
                "create_ceiling_plan": {
                    "type": "boolean",
                    "description": "Creates associated Reflected Ceiling Plan (RCP) if it does not already exist."
                },
                "create_structural_plan": {
                    "type": "boolean",
                    "description": "Creates associated Structural Plan if it does not already exist."
                },
                "view_template_id": {
                    "type": "string",
                    "description": "The UniqueId of a View Template to apply to newly generated views."
                }
            },
            "required": ["level_id"]
        }
    )
    def tool_modify_level(doc, tool_input):
        from Autodesk.Revit.DB import Transaction, Level, BuiltInParameter, ViewPlan, ViewFamily
        level_id = tool_input["level_id"]
        errors = []
        
        level = doc.GetElement(level_id)
        if not level or not isinstance(level, Level):
            return {
                "status": "error",
                "message": "Level element with UniqueId '{}' not found.".format(level_id)
            }
            
        pbp_x, pbp_y, pbp_z, pbp_err = get_base_point_offset(doc)
        if pbp_err:
            errors.append("Base point: " + pbp_err)
        
        new_name = tool_input.get("name")
        if new_name and new_name != level.Name:
            if not is_level_name_unique(doc, new_name, exclude_id=level.UniqueId):
                return {
                    "status": "error",
                    "message": "Level name '{}' is already in use in the active project.".format(new_name)
                }
                
        with Transaction(doc, "AI Agent - Modify Level") as trans:
            trans.Start()
            try:
                if new_name:
                    level.Name = new_name
                    
                if "elevation" in tool_input:
                    absolute_elevation = float(tool_input["elevation"]) + pbp_z
                    level.Elevation = absolute_elevation
                    
                if "is_structural" in tool_input:
                    is_struct = tool_input["is_structural"]
                    struct_param = level.get_Parameter(BuiltInParameter.LEVEL_IS_STRUCTURAL)
                    if struct_param and not struct_param.IsReadOnly:
                        struct_param.Set(1 if is_struct else 0)
                        
                if "level_type_id" in tool_input:
                    type_el = doc.GetElement(tool_input["level_type_id"])
                    if type_el:
                        level.ChangeTypeId(type_el.Id)
                        
                apply_datum_properties(doc, ui_app, level, tool_input, errors)
                
                # Generate views if requested and not already existing
                views_created = []
                view_temp_id = tool_input.get("view_template_id")
                
                if tool_input.get("create_floor_plan") is True:
                    if not has_plan_view(doc, level.Id, ViewFamily.FloorPlan):
                        vft = get_view_family_type(doc, ViewFamily.FloorPlan)
                        if vft:
                            vp = ViewPlan.Create(doc, vft.Id, level.Id)
                            if view_temp_id:
                                vt = doc.GetElement(view_temp_id)
                                if vt:
                                    vp.ViewTemplateId = vt.Id
                            views_created.append("Floor Plan: " + vp.Name)
                            
                if tool_input.get("create_ceiling_plan") is True:
                    if not has_plan_view(doc, level.Id, ViewFamily.CeilingPlan):
                        vft = get_view_family_type(doc, ViewFamily.CeilingPlan)
                        if vft:
                            vp = ViewPlan.Create(doc, vft.Id, level.Id)
                            if view_temp_id:
                                vt = doc.GetElement(view_temp_id)
                                if vt:
                                    vp.ViewTemplateId = vt.Id
                            views_created.append("RCP: " + vp.Name)
                            
                if tool_input.get("create_structural_plan") is True:
                    if not has_plan_view(doc, level.Id, ViewFamily.StructuralPlan):
                        vft = get_view_family_type(doc, ViewFamily.StructuralPlan)
                        if vft:
                            vp = ViewPlan.Create(doc, vft.Id, level.Id)
                            if view_temp_id:
                                vt = doc.GetElement(view_temp_id)
                                if vt:
                                    vp.ViewTemplateId = vt.Id
                            views_created.append("Structural Plan: " + vp.Name)
                            
                trans.Commit()
                level_id = level.UniqueId
            except Exception as ex:
                trans.RollBack()
                return {
                    "status": "error",
                    "message": "Failed to modify Level: {}".format(str(ex))
                }
                
        msg = "Successfully modified Level '{}'.".format(new_name or level.Name)
        if views_created:
            msg += " Generated views: {}.".format(", ".join(views_created))
            
        result = {
            "status": "success",
            "message": msg,
            "element_id": level_id
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="delete_level",
        description=(
            "Deletes an existing level from the active Revit project by its UniqueId. "
            "WARNING: Deleting a level also deletes all associated views (floor plans, ceiling plans, etc.) "
            "and any elements hosted on that level."
        ),
        agent_instructions=(
            "Before calling: Call fetch_levels to get the valid UniqueId for the level_id parameter. "
            "IMPORTANT: Always confirm with the user before deleting a level, as this will also delete "
            "associated views and hosted elements. This action cannot be undone."
        ),
        parameters={
            "type": "object",
            "properties": {
                "level_id": {
                    "type": "string",
                    "description": "The UniqueId of the Level to delete (from fetch_levels)."
                }
            },
            "required": ["level_id"]
        }
    )
    def tool_delete_level(doc, tool_input):
        from Autodesk.Revit.DB import Transaction, Level, FilteredElementCollector, ViewPlan, ElementId
        from System.Collections.Generic import List as NetList
        level_id = tool_input["level_id"]
        errors = []
        
        level = doc.GetElement(level_id)
        if not level or not isinstance(level, Level):
            return {
                "status": "error",
                "message": "Level element with UniqueId '{}' not found.".format(level_id)
            }
        
        level_name = level.Name or "Unnamed Level"
        
        with Transaction(doc, "AI Agent - Delete Level") as trans:
            trans.Start()
            try:
                # Collect all dependent elements (views, etc.) that reference this level
                dependent_ids = level.GetDependentElements(None)
                
                # Unpin the level itself before deleting
                if level.Pinned:
                    level.Pinned = False
                
                # Try to delete each dependent element individually
                # Some elements (like system views) may not be deletable
                deleted_count = 0
                for eid in dependent_ids:
                    if eid != ElementId.InvalidElementId and eid != level.Id:
                        dep_el = doc.GetElement(eid)
                        if dep_el:
                            if dep_el.Pinned:
                                dep_el.Pinned = False
                            try:
                                doc.Delete(eid)
                                deleted_count += 1
                            except Exception as e:
                                errors.append("Could not delete dependent element {}: {}".format(eid, str(e)))
                
                # Finally delete the level itself
                doc.Delete(level.Id)
                trans.Commit()
            except Exception as ex:
                trans.RollBack()
                return {
                    "status": "error",
                    "message": "Failed to delete Level '{}': {}".format(level_name, str(ex))
                }
        
        result = {
            "status": "success",
            "message": "Successfully deleted Level '{}' and all associated views/elements.".format(level_name)
        }
        if errors:
            result["warnings"] = errors
        return result

    @register_tool(
        name="create_sheet",
        description=(
            "Creates a new drawing sheet in the active Revit project using "
            "the first available Title Block family."
        ),
        agent_instructions=(
            "Before calling: "
            "(1) Call fetch_sheets to verify the sheet_number is not already used. "
            "Follow the project's existing sheet numbering convention as observed "
            "from the fetch_sheets results.\n"
            "(2) NEVER assume the sheet number or name — if the user has not specified them explicitly, "
            "ASK the user for the exact sheet_number and sheet_name before calling this tool."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sheet_number": {
                    "type":        "string",
                    "description": "Unique sheet identifier code (e.g. 'A101', 'A102')."
                },
                "sheet_name": {
                    "type":        "string",
                    "description": "Descriptive title of the sheet (e.g. 'FIRST FLOOR PLAN')."
                }
            },
            "required": ["sheet_number", "sheet_name"]
        }
    )
    def tool_create_sheet(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol, ViewSheet, Transaction
        sheet_number = tool_input.get("sheet_number", "A101")
        sheet_name   = tool_input.get("sheet_name",   "UNNAMED SHEET")
        errors = []

        collector = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
        title_block_symbol = None
        for symbol in collector:
            try:
                if symbol and symbol.Category and symbol.Category.Name == "Title Blocks":
                    title_block_symbol = symbol
                    break
            except Exception as e:
                errors.append("Skipped symbol: {}".format(str(e)))

        if not title_block_symbol:
            return {
                "status":  "error",
                "message": "No Title Block family is loaded in this project."
            }

        with Transaction(doc, "AI Agent - Create Sheet") as trans:
            trans.Start()
            new_sheet             = ViewSheet.Create(doc, title_block_symbol.Id)
            new_sheet.SheetNumber = sheet_number
            new_sheet.Name        = sheet_name
            trans.Commit()
            sheet_id = new_sheet.UniqueId

        return {
            "status":     "success",
            "message":    "Successfully created sheet {} - {}.".format(sheet_number, sheet_name),
            "element_id": sheet_id,
            "warnings":   errors if errors else None
        }

    @register_tool(
        name="fetch_level_extents_detailed",
        description="Fetches level extents across all elevation/section views to find the full X and Y bounds.",
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    def tool_fetch_level_extents_detailed(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Level, View, ViewType, DatumExtentType
        levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
        views = FilteredElementCollector(doc).OfClass(View).ToElements()
        
        x_min, x_max = None, None
        y_min, y_max = None, None
        
        for lvl in levels:
            for v in views:
                if not v or v.IsTemplate:
                    continue
                if v.ViewType == ViewType.Elevation or v.ViewType == ViewType.Section:
                    try:
                        model_curves = lvl.GetCurvesInView(DatumExtentType.Model, v)
                        if model_curves:
                            for curve in model_curves:
                                ep0 = curve.GetEndPoint(0)
                                ep1 = curve.GetEndPoint(1)
                                for pt in [ep0, ep1]:
                                    x = pt.X
                                    y = pt.Y
                                    if x_min is None or x < x_min: x_min = x
                                    if x_max is None or x > x_max: x_max = x
                                    if y_min is None or y < y_min: y_min = y
                                    if y_max is None or y > y_max: y_max = y
                    except Exception:
                        continue
        return {
            "status": "success",
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max
        }

    # -----------------------------------------------------------------
    # DISPATCH ROUTER
    # -----------------------------------------------------------------
    try:
        payload    = json.loads(request_json_string)
        tool_name  = payload.get("tool") or payload.get("action")
        tool_input = payload.get("input") or payload.get("parameters") or {}

        # Special: return the live tool registry (no Revit DB access needed)
        if tool_name == "get_tools":
            return json.dumps({"status": "success", "tools": tool_registry})

        # Special: query Revit project metadata
        if tool_name == "get_context":
            if ui_app is not None:
                doc = ui_app.ActiveUIDocument.Document
            else:
                doc = __revit__.ActiveUIDocument.Document
            return json.dumps(tool_get_context(doc, tool_input))

        # Registered tool dispatch
        if ui_app is not None:
            doc = ui_app.ActiveUIDocument.Document
        else:
            doc = __revit__.ActiveUIDocument.Document
        tool_fn = tool_functions.get(tool_name)

        if tool_fn:
            _log_debug(tool_name, "Executing with input: {}".format(json.dumps(tool_input)), level="DEBUG")
            _t0 = time.time()
            result = tool_fn(doc, tool_input)
            _elapsed = time.time() - _t0
        else:
            _t0 = None
            _elapsed = None
            result = {
                "status":  "error",
                "message": "Tool '{}' has no registered implementation inside Revit.".format(tool_name)
            }

        # Log result status and any warnings/errors
        result_status = result.get("status", "unknown")
        if result_status == "error":
            _log_debug(tool_name, "ERROR: {}".format(result.get("message", "unknown error")), level="ERROR")
        if result.get("warnings"):
            for w in result["warnings"]:
                _log_debug(tool_name, "WARNING: {}".format(w), level="WARN")
        if result.get("errors"):
            for e in result["errors"]:
                _log_debug(tool_name, "ERROR DETAIL: {}".format(e), level="ERROR")

        if _elapsed is not None:
            _log_debug(tool_name, "Completed with status: {} in {:.3f}s".format(result_status, _elapsed), level="INFO")
        else:
            _log_debug(tool_name, "Completed with status: {}".format(result_status), level="INFO")

        return json.dumps(result)

    except Exception as ex:
        _log_debug("dispatch", "FATAL: {}".format(str(ex)), level="FATAL")
        return json.dumps({"status": "error", "message": "Fatal exception in Python: " + str(ex)})


# =====================================================================
# EVENT REGISTRATION & SERVER TOGGLE
# pyRevit routes print() to its output panel — non-blocking and reliable.
# =====================================================================

if BridgeRegistry.ActiveServer is not None:
    # --- STOP ---
    try:
        BridgeRegistry.ActiveServer.Stop()
        BridgeRegistry.ActiveServer = None
        print(">>> AI Agent Bridge STOPPED.")
        print(">>> The server is no longer listening on port {}.".format(_PORT))
    except Exception as ex:
        print(">>> ERROR while stopping the bridge: " + str(ex))
else:
    # --- START ---
    try:
        handler = AgentExternalEventHandler()
        handler.PythonExecutor = python_execution_router

        external_event = ExternalEvent.Create(handler)

        bridge_server = BridgeServer(handler, external_event)
        bridge_server.Start(_PORT)

        BridgeRegistry.ActiveServer = bridge_server
        BridgeRegistry.ActiveEvent  = external_event

        print(">>> AI Agent Bridge STARTED — Listening on port {}.".format(_PORT))
        print(">>> Launch orchestrator.py in the daemon folder to begin a session.")
    except Exception as ex:
        print(">>> ERROR: Failed to start the Bridge Server: " + str(ex))