# -*- coding: utf-8 -*-
import clr
import os
import sys

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import ExternalEvent, TaskDialog

current_dir = os.path.dirname(__file__)
dll_full_path = os.path.join(current_dir, "RevitAgentBridge.dll")

if os.path.exists(dll_full_path):
    try:
        clr.AddReferenceToFileAndPath(dll_full_path)
    except Exception:
        sys.exit()
else:
    sys.exit()

from RevitAgentBridge import AgentExternalEventHandler, BridgeServer, BridgeRegistry

# =====================================================================
# DYNAMIC PYTHON EXECUTION ROUTER
#
# CRITICAL (IronPython GC rule): ALL registry state, helper functions,
# and tool implementations MUST live inside this closure. IronPython
# garbage-collects module-level globals after the script finishes.
# When C# calls PythonExecutor later, only the closure scope survives.
# =====================================================================

def python_execution_router(request_json_string):
    """
    Receives JSON payloads from C# on Revit's main thread.
    All state is kept inside this closure to survive IronPython GC.
    """
    import json
    from Autodesk.Revit.DB import (
        FilteredElementCollector, Level, FamilySymbol,
        Transaction, XYZ, Line, Grid, ViewSheet, Structure
    )

    # -----------------------------------------------------------------
    # IN-CLOSURE TOOL REGISTRY
    # Rebuilt on every call (fast), always consistent, GC-safe.
    # -----------------------------------------------------------------
    tool_registry  = []   # List of JSON schema dicts → served via GET /tools/
    tool_functions = {}   # Maps action name → tool function

    def register_tool(name, description, parameters):
        """
        IronPython 2.7-compatible decorator factory.
        Registers a tool's JSON schema and its implementation.

        Usage:
            @register_tool(
                name="my_action",
                description="Does something useful.",
                parameters={
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "..."}
                    },
                    "required": ["param1"]
                }
            )
            def tool_my_action(doc, parameters):
                ...
        """
        def decorator(fn):
            tool_registry.append({
                "name": name,
                "description": description,
                "parameters": parameters
            })
            tool_functions[name] = fn
            return fn
        return decorator

    # -----------------------------------------------------------------
    # SYSTEM TOOL: get_context (not exposed to Gemini, called directly)
    # -----------------------------------------------------------------

    def tool_get_context(doc, parameters):
        levels_list = []
        families_dict = {}

        level_collector = FilteredElementCollector(doc).OfClass(Level)
        for lvl in level_collector:
            try:
                if lvl:
                    levels_list.append({
                        "name": lvl.Name or "Unnamed Level",
                        "id": lvl.UniqueId,
                        "elevation": lvl.Elevation
                    })
            except Exception:
                continue

        symbol_collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        for symbol in symbol_collector:
            try:
                if symbol:
                    fam_name = symbol.FamilyName
                    type_name = symbol.Name
                    if fam_name:
                        if fam_name not in families_dict:
                            families_dict[fam_name] = []
                        if type_name and type_name not in families_dict[fam_name]:
                            families_dict[fam_name].append(type_name)
            except Exception:
                continue

        return {
            "status": "success",
            "document_title": doc.Title or "Untitled",
            "levels": levels_list,
            "families": families_dict
        }

    # -----------------------------------------------------------------
    # REGISTERED FETCH TOOLS (Read-only context queries for Gemini)
    # -----------------------------------------------------------------

    @register_tool(
        name="fetch_project_info",
        description=(
            "Fetches basic identification metadata about the active Revit "
            "project. Returns the document title and file path. Use this "
            "for lightweight project identification."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    def tool_fetch_project_info(doc, parameters):
        file_path = ""
        try:
            if doc.PathName:
                file_path = doc.PathName
        except Exception:
            pass

        return {
            "status": "success",
            "document_title": doc.Title or "Untitled",
            "file_path": file_path
        }

    @register_tool(
        name="fetch_levels",
        description=(
            "Fetches all levels in the active Revit project. Returns each "
            "level's name, UniqueId, and elevation in feet. Use this before "
            "placing family instances or when you need elevation context."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    def tool_fetch_levels(doc, parameters):
        levels_list = []
        level_collector = FilteredElementCollector(doc).OfClass(Level)
        for lvl in level_collector:
            try:
                if lvl:
                    levels_list.append({
                        "name": lvl.Name or "Unnamed Level",
                        "id": lvl.UniqueId,
                        "elevation": lvl.Elevation
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
            "project. Returns each grid's name, UniqueId, and the start/end "
            "point coordinates of its curve. Use this before creating new "
            "grids to check names and determine spacing."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    def tool_fetch_grids(doc, parameters):
        grids_list = []
        grid_collector = FilteredElementCollector(doc).OfClass(Grid)
        for grid in grid_collector:
            try:
                if grid:
                    curve = grid.Curve
                    start_pt = curve.GetEndPoint(0)
                    end_pt = curve.GetEndPoint(1)
                    grids_list.append({
                        "name": grid.Name or "Unnamed Grid",
                        "id": grid.UniqueId,
                        "start_point": {
                            "x": start_pt.X,
                            "y": start_pt.Y,
                            "z": start_pt.Z
                        },
                        "end_point": {
                            "x": end_pt.X,
                            "y": end_pt.Y,
                            "z": end_pt.Z
                        }
                    })
            except Exception:
                continue

        return {
            "status": "success",
            "grids": grids_list
        }

    @register_tool(
        name="fetch_families",
        description=(
            "Fetches all loaded family symbols (types) in the active Revit "
            "project. Returns a dictionary mapping family names to lists of "
            "their available type names. Use this before placing a family "
            "instance to verify the family and type are loaded."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    def tool_fetch_families(doc, parameters):
        families_dict = {}
        symbol_collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        for symbol in symbol_collector:
            try:
                if symbol:
                    fam_name = symbol.FamilyName
                    type_name = symbol.Name
                    if fam_name:
                        if fam_name not in families_dict:
                            families_dict[fam_name] = []
                        if type_name and type_name not in families_dict[fam_name]:
                            families_dict[fam_name].append(type_name)
            except Exception:
                continue

        return {
            "status": "success",
            "families": families_dict
        }

    @register_tool(
        name="fetch_sheets",
        description=(
            "Fetches all existing drawing sheets in the active Revit project. "
            "Returns each sheet's number, name, and UniqueId. Use this before "
            "creating a new sheet to avoid duplicate sheet numbers."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": []
        }
    )
    def tool_fetch_sheets(doc, parameters):
        sheets_list = []
        sheet_collector = FilteredElementCollector(doc).OfClass(ViewSheet)
        for sheet in sheet_collector:
            try:
                if sheet:
                    sheets_list.append({
                        "number": sheet.SheetNumber or "",
                        "name": sheet.Name or "Unnamed Sheet",
                        "id": sheet.UniqueId
                    })
            except Exception:
                continue

        return {
            "status": "success",
            "sheets": sheets_list
        }

    # -----------------------------------------------------------------
    # REGISTERED ACTION TOOLS (Exposed to Gemini via GET /tools/)
    # -----------------------------------------------------------------

    @register_tool(
        name="place_family",
        description=(
            "Places a loaded family symbol instance at a specified 3D "
            "coordinate on a given level in the active Revit project."
        ),
        parameters={
            "type": "object",
            "properties": {
                "family_name": {
                    "type": "string",
                    "description": "The exact name of the family (e.g. 'Single-Flush')."
                },
                "type_name": {
                    "type": "string",
                    "description": "The type name within the family (e.g. '36\" x 84\"')."
                },
                "level_id": {
                    "type": "string",
                    "description": "The UniqueId of the host level element."
                },
                "x": {
                    "type": "number",
                    "description": "X coordinate in feet."
                },
                "y": {
                    "type": "number",
                    "description": "Y coordinate in feet."
                },
                "z": {
                    "type": "number",
                    "description": "Z coordinate in feet."
                }
            },
            "required": ["family_name", "type_name", "level_id", "x", "y", "z"]
        }
    )
    def tool_place_family(doc, parameters):
        family_name = parameters.get("family_name")
        type_name   = parameters.get("type_name")
        level_id    = parameters.get("level_id")
        x = parameters.get("x", 0.0)
        y = parameters.get("y", 0.0)
        z = parameters.get("z", 0.0)

        level_el = doc.GetElement(level_id)
        if not level_el or not isinstance(level_el, Level):
            return {"status": "error", "message": "Invalid level ID."}

        target_symbol = None
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
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
                "status": "error",
                "message": "Symbol '{}-{}' is not loaded.".format(family_name, type_name)
            }

        with Transaction(doc, "AI Agent - Place Family") as trans:
            trans.Start()
            if not target_symbol.IsActive:
                target_symbol.Activate()
                doc.Regenerate()
            point    = XYZ(float(x), float(y), float(z))
            instance = doc.Create.NewFamilyInstance(
                point, target_symbol, level_el,
                Structure.StructuralType.NonStructural
            )
            trans.Commit()
            placed_id = instance.UniqueId

        return {
            "status": "success",
            "message": "Successfully placed element.",
            "element_id": placed_id
        }

    @register_tool(
        name="create_grid",
        description=(
            "Creates a linear reference gridline between two XY points "
            "in the active Revit project."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Display name of the grid (e.g. 'Grid A', 'Grid 1')."
                },
                "start_x": {
                    "type": "number",
                    "description": "Starting X coordinate in feet."
                },
                "start_y": {
                    "type": "number",
                    "description": "Starting Y coordinate in feet."
                },
                "end_x": {
                    "type": "number",
                    "description": "Ending X coordinate in feet."
                },
                "end_y": {
                    "type": "number",
                    "description": "Ending Y coordinate in feet."
                }
            },
            "required": ["name", "start_x", "start_y", "end_x", "end_y"]
        }
    )
    def tool_create_grid(doc, parameters):
        grid_name = parameters.get("name")
        start_x   = parameters.get("start_x", 0.0)
        start_y   = parameters.get("start_y", 0.0)
        end_x     = parameters.get("end_x", 0.0)
        end_y     = parameters.get("end_y", 0.0)

        with Transaction(doc, "AI Agent - Create Grid") as trans:
            trans.Start()
            start_point = XYZ(float(start_x), float(start_y), 0.0)
            end_point   = XYZ(float(end_x), float(end_y), 0.0)
            grid_line   = Line.CreateBound(start_point, end_point)
            new_grid    = Grid.Create(doc, grid_line)
            if grid_name:
                new_grid.Name = grid_name
            trans.Commit()
            grid_id = new_grid.UniqueId

        return {
            "status": "success",
            "message": "Successfully created Grid '{}'.".format(grid_name),
            "element_id": grid_id
        }

    @register_tool(
        name="create_sheet",
        description=(
            "Creates a new drawing sheet in the active Revit project using "
            "the first available Title Block family."
        ),
        parameters={
            "type": "object",
            "properties": {
                "sheet_number": {
                    "type": "string",
                    "description": "Unique sheet identifier code (e.g. 'A101', 'A102')."
                },
                "sheet_name": {
                    "type": "string",
                    "description": "Descriptive title of the sheet (e.g. 'FIRST FLOOR PLAN')."
                }
            },
            "required": ["sheet_number", "sheet_name"]
        }
    )
    def tool_create_sheet(doc, parameters):
        sheet_number = parameters.get("sheet_number", "A101")
        sheet_name   = parameters.get("sheet_name", "UNNAMED SHEET")

        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        title_block_symbol = None
        for symbol in collector:
            try:
                if symbol and symbol.Category and symbol.Category.Name == "Title Blocks":
                    title_block_symbol = symbol
                    break
            except Exception:
                continue

        if not title_block_symbol:
            return {"status": "error", "message": "No Title Block family loaded in this project."}

        with Transaction(doc, "AI Agent - Create Sheet") as trans:
            trans.Start()
            new_sheet = ViewSheet.Create(doc, title_block_symbol.Id)
            new_sheet.SheetNumber = sheet_number
            new_sheet.Name = sheet_name
            trans.Commit()
            sheet_id = new_sheet.UniqueId

        return {
            "status": "success",
            "message": "Successfully created sheet {} - {}.".format(sheet_number, sheet_name),
            "element_id": sheet_id
        }

    # -----------------------------------------------------------------
    # DISPATCH ROUTER
    # -----------------------------------------------------------------
    try:
        payload    = json.loads(request_json_string)
        action     = payload.get("action")
        parameters = payload.get("parameters", {})

        # Special: return the live tool registry (no Revit DB access needed)
        if action == "get_tools":
            return json.dumps({"status": "success", "tools": tool_registry})

        # Special: query Revit project metadata
        if action == "get_context":
            doc = __revit__.ActiveUIDocument.Document
            return json.dumps(tool_get_context(doc, parameters))

        # Registered tool dispatch
        doc     = __revit__.ActiveUIDocument.Document
        tool_fn = tool_functions.get(action)

        if tool_fn:
            result = tool_fn(doc, parameters)
        else:
            result = {
                "status": "error",
                "message": "Action '{}' has no registered implementation inside Revit.".format(action)
            }

        return json.dumps(result)

    except Exception as ex:
        return json.dumps({"status": "error", "message": "Fatal exception in Python: " + str(ex)})


# =====================================================================
# EVENT REGISTRATION & TOGGLE
# =====================================================================

from pyrevit import script as pvscript

def update_button_ui(is_active):
    """
    Updates the Ribbon button title and shows a confirmation dialog.
    pyRevit exposes the live button reference via script.get_button().
    The correct property for runtime title updates is ui_title.
    """
    try:
        button = pvscript.get_button()
        if button is not None:
            if is_active:
                button.ui_title = "Stop Bridge\n[ACTIVE]"
            else:
                button.ui_title = "Start Bridge\n[OFF]"
    except Exception:
        pass  # Title update is best-effort; dialog feedback is the reliable path

    if is_active:
        TaskDialog.Show("AI Agent Bridge", "Bridge Server is now ACTIVE and listening on port 8080.")
    else:
        TaskDialog.Show("AI Agent Bridge", "Bridge Server has been STOPPED.")


def stop_active_bridge():
    try:
        active_server = BridgeRegistry.ActiveServer
        if active_server is not None:
            active_server.Stop()
            BridgeRegistry.ActiveServer = None
    except Exception:
        pass


# Toggle execution logic
if BridgeRegistry.ActiveServer is not None:
    stop_active_bridge()
    update_button_ui(False)
else:
    try:
        handler = AgentExternalEventHandler()
        handler.PythonExecutor = python_execution_router

        external_event = ExternalEvent.Create(handler)

        bridge_server = BridgeServer(handler, external_event)
        bridge_server.Start(8080)

        BridgeRegistry.ActiveServer = bridge_server
        BridgeRegistry.ActiveEvent  = external_event

        update_button_ui(True)
    except Exception as start_ex:
        TaskDialog.Show("AI Agent Bridge", "Failed to start Bridge Server:\n" + str(start_ex))