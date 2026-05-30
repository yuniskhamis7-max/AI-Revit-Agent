# -*- coding: utf-8 -*-
import clr
import os
import sys

# Reference internal Revit API namespaces
from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import ExternalEvent

current_dir = os.path.dirname(__file__)
dll_full_path = os.path.join(current_dir, "RevitAgentBridge.dll")

# Safely resolve binary dependencies
if os.path.exists(dll_full_path):
    try:
        clr.AddReferenceToFileAndPath(dll_full_path)
    except Exception as ex:
        sys.exit()
else:
    sys.exit()

from RevitAgentBridge import AgentExternalEventHandler, BridgeServer, BridgeRegistry

# =====================================================================
# DYNAMIC PYTHON EXECUTION ROUTER (WITH CLOSURE PROTECTION)
# =====================================================================

def python_execution_router(request_json_string):
    """
    Receives JSON payloads directly from C# on Revit's main thread.
    Contains all nested tools inside its closure scope to prevent garbage collection.
    """
    import json
    from Autodesk.Revit.DB import (
        FilteredElementCollector, Level, FamilySymbol, 
        Transaction, XYZ, Line, Grid, ViewSheet, Structure
    )
    
    # -----------------------------------------------------------------
    # NESTED CLOSURE TOOLS (With Defensive Null Checks)
    # -----------------------------------------------------------------
    
    def tool_get_context(doc, parameters):
        levels_list = []
        families_dict = {}

        # Safe Level Extraction
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

        # Safe Family Symbol Extraction (Skip system/null elements)
        symbol_collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        for symbol in symbol_collector:
            try:
                # Ensure the symbol and its parent Family object are not null
                if symbol and symbol.Family:
                    fam_name = symbol.Family.Name
                    type_name = symbol.Name
                    
                    if fam_name:
                        if fam_name not in families_dict:
                            families_dict[fam_name] = []
                        if type_name and type_name not in families_dict[fam_name]:
                            families_dict[fam_name].append(type_name)
            except Exception:
                # Safely skip elements that throw exceptions during property reads
                continue

        return {
            "status": "success",
            "document_title": doc.Title or "test",
            "levels": levels_list,
            "families": families_dict
        }

    def tool_place_family(doc, parameters):
        family_name = parameters.get("family_name")
        type_name = parameters.get("type_name")
        level_id = parameters.get("level_id")
        coords = parameters.get("coordinates", {"x": 0.0, "y": 0.0, "z": 0.0})

        level_el = doc.GetElement(level_id)
        if not level_el or not isinstance(level_el, Level):
            return {"status": "error", "message": "Invalid level ID."}

        target_symbol = None
        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        for s in collector:
            try:
                if s and s.Family:
                    if s.Family.Name.lower() == family_name.lower() and s.Name.lower() == type_name.lower():
                        target_symbol = s
                        break
            except Exception:
                continue

        if not target_symbol:
            return {"status": "error", "message": "Symbol '{}-{}' is not loaded.".format(family_name, type_name)}

        with Transaction(doc, "AI Agent - Place Family") as trans:
            trans.Start()
            if not target_symbol.IsActive:
                target_symbol.Activate()
                doc.Regenerate()
            
            point = XYZ(coords.get("x", 0.0), coords.get("y", 0.0), coords.get("z", 0.0))
            instance = doc.Create.NewFamilyInstance(
                point, 
                target_symbol, 
                level_el, 
                Structure.StructuralType.NonStructural
            )
            trans.Commit()
            placed_id = instance.UniqueId

        return {
            "status": "success",
            "message": "Successfully placed element.",
            "element_id": placed_id
        }

    def tool_create_grid(doc, parameters):
        grid_name = parameters.get("name")
        start = parameters.get("start_point", {"x": 0.0, "y": 0.0})
        end = parameters.get("end_point", {"x": 0.0, "y": 0.0})

        with Transaction(doc, "AI Agent - Create Grid") as trans:
            trans.Start()
            start_point = XYZ(start.get("x", 0.0), start.get("y", 0.0), 0.0)
            end_point = XYZ(end.get("x", 0.0), end.get("y", 0.0), 0.0)
            
            grid_line = Line.CreateBound(start_point, end_point)
            new_grid = Grid.CreateGrid(doc, grid_line)
            if grid_name:
                new_grid.Name = grid_name
            trans.Commit()
            grid_id = new_grid.UniqueId

        return {
            "status": "success",
            "message": "Successfully created Grid '{}'".format(grid_name),
            "element_id": grid_id
        }

    def tool_create_sheet(doc, parameters):
        sheet_number = parameters.get("sheet_number", "A101")
        sheet_name = parameters.get("sheet_name", "UNNAMED SHEET")

        collector = FilteredElementCollector(doc).OfClass(FamilySymbol)
        title_block_symbol = None
        for symbol in collector:
            try:
                # Ensure category is not null before checking category name
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
            "message": "Successfully created sheet {} - {}".format(sheet_number, sheet_name),
            "element_id": sheet_id
        }

    # -----------------------------------------------------------------
    # ROUTER EXECUTION DISPATCH
    # -----------------------------------------------------------------
    try:
        payload = json.loads(request_json_string)
        action = payload.get("action")
        parameters = payload.get("parameters", {})

        doc = __revit__.ActiveUIDocument.Document

        if action == "get_context":
            result = tool_get_context(doc, parameters)
        elif action == "place_family":
            result = tool_place_family(doc, parameters)
        elif action == "create_grid":
            result = tool_create_grid(doc, parameters)
        elif action == "create_sheet":
            result = tool_create_sheet(doc, parameters)
        else:
            result = {"status": "error", "message": "Action '{}' has no python implementation.".format(action)}

        return json.dumps(result)
        
    except Exception as ex:
        return json.dumps({"status": "error", "message": "Fatal exception in Python: " + str(ex)})

# =====================================================================
# EVENT REGISTRATION & TOGGLE
# =====================================================================

def stop_active_bridge():
    try:
        active_server = BridgeRegistry.ActiveServer
        if active_server is not None:
            active_server.Stop()
            BridgeRegistry.ActiveServer = None
    except Exception:
         pass

if BridgeRegistry.ActiveServer is not None:
    stop_active_bridge()
else:
    try:
        handler = AgentExternalEventHandler()
        
        # BIND THE PYTHON ROUTER DIRECTLY TO THE C# EVENT HANDLER
        handler.PythonExecutor = python_execution_router

        external_event = ExternalEvent.Create(handler)

        bridge_server = BridgeServer(handler, external_event)
        bridge_server.Start(8080)

        BridgeRegistry.ActiveServer = bridge_server
        BridgeRegistry.ActiveEvent = external_event
    except Exception:
        pass