# -*- coding: utf-8 -*-
import clr
import os
import sys

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import ExternalEvent

current_dir   = os.path.dirname(__file__)
dll_full_path = os.path.join(current_dir, "RevitAgentBridge.dll")

if os.path.exists(dll_full_path):
    try:
        clr.AddReferenceToFileAndPath(dll_full_path)
    except Exception:
        print(">>> ERROR: Could not load RevitAgentBridge.dll.")
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

    if len(args) == 2:
        ui_app, request_json_string = args
    else:
        ui_app = None
        request_json_string = args[0]

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
        try:
            collector = FilteredElementCollector(doc).OfClass(BasePoint)
            for bp in collector:
                try:
                    if not bp.IsShared:
                        east  = bp.get_Parameter(BuiltInParameter.BASEPOINT_EASTWEST_PARAM).AsDouble()
                        north = bp.get_Parameter(BuiltInParameter.BASEPOINT_NORTHSOUTH_PARAM).AsDouble()
                        elev  = bp.get_Parameter(BuiltInParameter.BASEPOINT_ELEVATION_PARAM).AsDouble()
                        return east, north, elev
                except Exception:
                    continue
        except Exception:
            pass
        return 0.0, 0.0, 0.0

    # -----------------------------------------------------------------
    # SYSTEM TOOL: get_context (internal, not in registered list)
    # -----------------------------------------------------------------
    def tool_get_context(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Level, FamilySymbol
        pbp_x, pbp_y, pbp_z = get_base_point_offset(doc)
        levels_list   = []
        families_dict = {}

        level_collector = FilteredElementCollector(doc).OfClass(Level).ToElements()
        for lvl in level_collector:
            try:
                if lvl:
                    levels_list.append({
                        "name":      lvl.Name or "Unnamed Level",
                        "id":        lvl.UniqueId,
                        "elevation": lvl.Elevation - pbp_z
                    })
            except Exception:
                continue

        symbol_collector = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
        for symbol in symbol_collector:
            try:
                if symbol:
                    fam_name = None
                    try:
                        fam_name = symbol.FamilyName
                    except Exception:
                        pass
                    if not fam_name:
                        try:
                            fam_name = symbol.Family.Name
                        except Exception:
                            pass
                    if not fam_name:
                        try:
                            fam_name = symbol.Category.Name
                        except Exception:
                            pass

                    type_name = symbol.Name
                    if fam_name:
                        if fam_name not in families_dict:
                            families_dict[fam_name] = []
                        if type_name and type_name not in families_dict[fam_name]:
                            families_dict[fam_name].append(type_name)
            except Exception:
                continue

        return {
            "status":         "success",
            "document_title": doc.Title or "Untitled",
            "levels":         levels_list,
            "families":       families_dict
        }

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
        try:
            if doc.PathName:
                file_path = doc.PathName
        except Exception:
            pass

        return {
            "status":         "success",
            "document_title": doc.Title or "Untitled",
            "file_path":      file_path
        }

    @register_tool(
        name="fetch_levels",
        description=(
            "Fetches all levels in the active Revit project. Returns each "
            "level's name, UniqueId, and elevation in feet relative to the Project Base Point."
        ),
        agent_instructions=(
            "Call before any tool that requires a level_id. "
            "Use the returned 'id' (UniqueId) as-is for the level_id argument "
            "— never use the level name as an id. "
            "Match level names to the user's intent (e.g. 'ground floor' maps to 'Level 1'). "
            "Elevations are in feet relative to the Project Base Point."
        ),
        parameters={
            "type":       "object",
            "properties": {},
            "required":   []
        }
    )
    def tool_fetch_levels(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Level
        pbp_x, pbp_y, pbp_z = get_base_point_offset(doc)
        levels_list = []
        level_collector = FilteredElementCollector(doc).OfClass(Level).ToElements()
        for lvl in level_collector:
            try:
                if lvl:
                    levels_list.append({
                        "name":      lvl.Name or "Unnamed Level",
                        "id":        lvl.UniqueId,
                        "elevation": lvl.Elevation - pbp_z
                    })
            except Exception:
                continue

        return {
            "status": "success",
            "levels": levels_list
        }

    @register_tool(
        name="fetch_grids",
        description=(
            "Fetches all existing reference gridlines in the active Revit "
            "project. Returns each grid's name, UniqueId, and start/end "
            "point coordinates relative to the Project Base Point in feet."
        ),
        agent_instructions=(
            "Call before create_grid. "
            "Verify no grid with the target name already exists. "
            "Returned coordinates are relative to the Project Base Point in feet "
            "— use these to determine correct spacing and extents for new grids."
        ),
        parameters={
            "type":       "object",
            "properties": {},
            "required":   []
        }
    )
    def tool_fetch_grids(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, Grid
        pbp_x, pbp_y, pbp_z = get_base_point_offset(doc)

        grids_list = []
        grid_collector = FilteredElementCollector(doc).OfClass(Grid).ToElements()
        for grid in grid_collector:
            try:
                if grid:
                    curve    = grid.Curve
                    start_pt = curve.GetEndPoint(0)
                    end_pt   = curve.GetEndPoint(1)
                    grids_list.append({
                        "name": grid.Name or "Unnamed Grid",
                        "id":   grid.UniqueId,
                        "start_point": {
                            "x": start_pt.X - pbp_x,
                            "y": start_pt.Y - pbp_y,
                            "z": start_pt.Z - pbp_z
                        },
                        "end_point": {
                            "x": end_pt.X - pbp_x,
                            "y": end_pt.Y - pbp_y,
                            "z": end_pt.Z - pbp_z
                        }
                    })
            except Exception:
                continue

        return {
            "status":               "success",
            "coordinate_reference": "Project Base Point",
            "grids":                grids_list
        }

    @register_tool(
        name="fetch_families",
        description=(
            "Fetches all loaded family symbols (types) in the active Revit "
            "project. Returns a dictionary mapping family names to lists of "
            "their available type names."
        ),
        agent_instructions=(
            "Call before place_family. "
            "Use the exact family_name and type_name strings as returned "
            "— do not approximate or guess names. "
            "If the required family is not in the list, inform the user it is "
            "not loaded in the project."
        ),
        parameters={
            "type":       "object",
            "properties": {},
            "required":   []
        }
    )
    def tool_fetch_families(doc, tool_input):
        from Autodesk.Revit.DB import FilteredElementCollector, FamilySymbol
        families_dict = {}
        symbol_collector = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
        for symbol in symbol_collector:
            try:
                if symbol:
                    fam_name = None
                    try:
                        fam_name = symbol.FamilyName
                    except Exception:
                        pass
                    if not fam_name:
                        try:
                            fam_name = symbol.Family.Name
                        except Exception:
                            pass
                    if not fam_name:
                        try:
                            fam_name = symbol.Category.Name
                        except Exception:
                            pass

                    type_name = symbol.Name
                    if fam_name:
                        if fam_name not in families_dict:
                            families_dict[fam_name] = []
                        if type_name and type_name not in families_dict[fam_name]:
                            families_dict[fam_name].append(type_name)
            except Exception:
                continue

        return {
            "status":   "success",
            "families": families_dict
        }

    @register_tool(
        name="fetch_sheets",
        description=(
            "Fetches all existing drawing sheets in the active Revit project. "
            "Returns each sheet's number, name, and UniqueId."
        ),
        agent_instructions=(
            "Call before create_sheet. "
            "Confirm no sheet with the same sheet_number already exists. "
            "Observe the existing numbering convention from the results."
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
        sheet_collector = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
        for sheet in sheet_collector:
            try:
                if sheet:
                    sheets_list.append({
                        "number": sheet.SheetNumber or "",
                        "name":   sheet.Name or "Unnamed Sheet",
                        "id":     sheet.UniqueId
                    })
            except Exception:
                continue

        return {
            "status": "success",
            "sheets": sheets_list
        }

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
            "Use z=0.0 for level-hosted families unless the user explicitly specifies otherwise."
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
        for s in collector:
            try:
                if s:
                    if (s.FamilyName.lower() == family_name.lower() and
                            s.Name.lower() == type_name.lower()):
                        target_symbol = s
                        break
            except Exception:
                continue

        if not target_symbol:
            return {
                "status":  "error",
                "message": "Symbol '{} - {}' is not loaded. Call fetch_families to verify available names.".format(
                    family_name, type_name
                )
            }

        pbp_x, pbp_y, pbp_z = get_base_point_offset(doc)

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
            "Creates a linear reference gridline between two XY points "
            "in the active Revit project."
        ),
        agent_instructions=(
            "Before calling: "
            "(1) Call fetch_grids to check existing grid names and determine spacing. "
            "All coordinates are relative to the Project Base Point in feet. "
            "Extend grid lines at least 10 feet beyond the outermost building "
            "element on each end."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type":        "string",
                    "description": "Display name of the grid (e.g. 'A', '1')."
                },
                "start_x": {
                    "type":        "number",
                    "description": "Starting X coordinate in feet, relative to the Project Base Point."
                },
                "start_y": {
                    "type":        "number",
                    "description": "Starting Y coordinate in feet, relative to the Project Base Point."
                },
                "end_x": {
                    "type":        "number",
                    "description": "Ending X coordinate in feet, relative to the Project Base Point."
                },
                "end_y": {
                    "type":        "number",
                    "description": "Ending Y coordinate in feet, relative to the Project Base Point."
                }
            },
            "required": ["name", "start_x", "start_y", "end_x", "end_y"]
        }
    )
    def tool_create_grid(doc, tool_input):
        from Autodesk.Revit.DB import Transaction, XYZ, Line, Grid
        grid_name = tool_input.get("name")
        start_x   = float(tool_input.get("start_x", 0.0))
        start_y   = float(tool_input.get("start_y", 0.0))
        end_x     = float(tool_input.get("end_x",   0.0))
        end_y     = float(tool_input.get("end_y",   0.0))

        pbp_x, pbp_y, _ = get_base_point_offset(doc)

        with Transaction(doc, "AI Agent - Create Grid") as trans:
            trans.Start()
            start_point = XYZ(start_x + pbp_x, start_y + pbp_y, 0.0)
            end_point   = XYZ(end_x   + pbp_x, end_y   + pbp_y, 0.0)
            grid_line   = Line.CreateBound(start_point, end_point)
            new_grid    = Grid.Create(doc, grid_line)
            if grid_name:
                new_grid.Name = grid_name
            trans.Commit()
            grid_id = new_grid.UniqueId

        return {
            "status":     "success",
            "message":    "Successfully created Grid '{}'.".format(grid_name),
            "element_id": grid_id
        }

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
            "from the fetch_sheets results."
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

        collector = FilteredElementCollector(doc).OfClass(FamilySymbol).ToElements()
        title_block_symbol = None
        for symbol in collector:
            try:
                if symbol and symbol.Category and symbol.Category.Name == "Title Blocks":
                    title_block_symbol = symbol
                    break
            except Exception:
                continue

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
            "element_id": sheet_id
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
            result = tool_fn(doc, tool_input)
        else:
            result = {
                "status":  "error",
                "message": "Tool '{}' has no registered implementation inside Revit.".format(tool_name)
            }

        return json.dumps(result)

    except Exception as ex:
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
        print(">>> The server is no longer listening on port 8080.")
    except Exception as ex:
        print(">>> ERROR while stopping the bridge: " + str(ex))
else:
    # --- START ---
    try:
        handler = AgentExternalEventHandler()
        handler.PythonExecutor = python_execution_router

        external_event = ExternalEvent.Create(handler)

        bridge_server = BridgeServer(handler, external_event)
        bridge_server.Start(8080)

        BridgeRegistry.ActiveServer = bridge_server
        BridgeRegistry.ActiveEvent  = external_event

        print(">>> AI Agent Bridge STARTED — Listening on port 8080.")
        print(">>> Launch orchestrator.py in the daemon folder to begin a session.")
    except Exception as ex:
        print(">>> ERROR: Failed to start the Bridge Server: " + str(ex))