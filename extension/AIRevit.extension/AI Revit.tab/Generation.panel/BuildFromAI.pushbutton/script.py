#! python3
# -*- coding: utf-8 -*-
__title__ = 'Build\nFrom AI'
__author__ = 'BIM Manager'

import Autodesk.Revit.DB as DB
import Autodesk.Revit.UI as UI
import os
import sys
import importlib

current_dir = os.path.dirname(__file__)
lib_path = os.path.abspath(os.path.join(current_dir, "../../../../../lib"))
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

import dtos
import payload_manager
import coordinate_utility
import revit_managers.level_manager
import revit_managers.grid_manager

importlib.reload(dtos)
importlib.reload(payload_manager)
importlib.reload(coordinate_utility)
importlib.reload(revit_managers.level_manager)
importlib.reload(revit_managers.grid_manager)

from payload_manager import PayloadManager
from coordinate_utility import CoordinateUtility
from revit_managers.level_manager import LevelManager
from revit_managers.grid_manager import GridManager

doc = __revit__.ActiveUIDocument.Document

# High-fidelity simulated Multi-Use Tower structural data payload
AI_JSON_PAYLOAD = """
{
    "settings": {
        "grids_unit": "mm",
        "levels_unit": "mm",
        "coordinate_system": "project_base_point"
    },
    "level_strategy": {
        "mode": "explicit",
        "link_name": null,
        "prefix_copied_levels": ""
    },
    "grid_strategy": {
        "mode": "explicit",
        "link_name": null,
        "prefix_copied_grids": ""
    },
    "levels": [
        {"id": "lvl_b2", "name": "B2 - Foundation Slab", "elevation": -7200.0, "is_pinned": true, "create_floor_plan": false},
        {"id": "lvl_b1", "name": "B1 - Parking Garage", "elevation": -3600.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l0", "name": "L0 - Entrance Lobby (PBP)", "elevation": 0.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l1", "name": "L1 - Retail Mezzanine", "elevation": 4800.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l2", "name": "L2 - Office Typical 01", "elevation": 9000.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l3", "name": "L3 - Office Typical 02", "elevation": 12800.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l4", "name": "L4 - Office Typical 03", "elevation": 16600.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l5", "name": "L5 - Mechanical & Plant", "elevation": 20400.0, "is_pinned": true, "create_floor_plan": false},
        {"id": "lvl_l6", "name": "L6 - Residential Amenity", "elevation": 24600.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l7", "name": "L7 - Residential Typical 01", "elevation": 27800.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l8", "name": "L8 - Residential Typical 02", "elevation": 31000.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l9", "name": "L9 - Residential Typical 03", "elevation": 34200.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_l10", "name": "L10 - Penthouse Suite", "elevation": 37400.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_roof", "name": "Roof Deck / Terrace", "elevation": 41200.0, "is_pinned": true, "create_floor_plan": true},
        {"id": "lvl_para", "name": "Top of Parapet", "elevation": 42700.0, "is_pinned": false, "create_floor_plan": false}
    ],
    "grids": [
        {"id": "g_1", "name": "1", "start": {"x": 0.0, "y": -4000.0}, "end": {"x": 0.0, "y": 44000.0}, "is_pinned": true},
        {"id": "g_2", "name": "2", "start": {"x": 6000.0, "y": -4000.0}, "end": {"x": 6000.0, "y": 44000.0}, "is_pinned": true},
        {"id": "g_3", "name": "3", "start": {"x": 14000.0, "y": -4000.0}, "end": {"x": 14000.0, "y": 44000.0}, "is_pinned": true},
        {"id": "g_4", "name": "4", "start": {"x": 22000.0, "y": -4000.0}, "end": {"x": 22000.0, "y": 44000.0}, "is_pinned": true},
        {"id": "g_5", "name": "5", "start": {"x": 28000.0, "y": -4000.0}, "end": {"x": 28000.0, "y": 44000.0}, "is_pinned": true},
        {"id": "g_6", "name": "6", "start": {"x": 37000.0, "y": -4000.0}, "end": {"x": 37000.0, "y": 44000.0}, "is_pinned": true},
        
        {"id": "g_a", "name": "A", "start": {"x": -4000.0, "y": 0.0}, "end": {"x": 41000.0, "y": 0.0}, "is_pinned": true},
        {"id": "g_b", "name": "B", "start": {"x": -4000.0, "y": 7500.0}, "end": {"x": 41000.0, "y": 7500.0}, "is_pinned": true},
        {"id": "g_c", "name": "C", "start": {"x": -4000.0, "y": 15000.0}, "end": {"x": 41000.0, "y": 15000.0}, "is_pinned": true},
        {"id": "g_d", "name": "D", "start": {"x": -4000.0, "y": 21000.0}, "end": {"x": 41000.0, "y": 21000.0}, "is_pinned": true},
        {"id": "g_e", "name": "E", "start": {"x": -4000.0, "y": 29500.0}, "end": {"x": 41000.0, "y": 29500.0}, "is_pinned": true},
        {"id": "g_f", "name": "F", "start": {"x": -4000.0, "y": 38000.0}, "end": {"x": 41000.0, "y": 38000.0}, "is_pinned": true}
    ]
}
"""

def generate_dry_run_report(p_data, level_mgr, grid_mgr) -> str:
    """Pre-flight dry-run check displaying original payload coordinates."""
    levels_to_create = []
    levels_to_update = []
    grids_to_create = []
    grids_to_update = []

    l_unit = p_data.settings.levels_unit
    g_unit = p_data.settings.grids_unit
    
    l_mult = PayloadManager.UNIT_MULTIPLIERS.get(l_unit.lower(), 1.0)

    # Process Levels
    for l_data in p_data.levels:
        display_elevation = round(l_data.elevation / l_mult, 1)
        existing = level_mgr._level_cache.get(l_data.id) or level_mgr._level_cache.get(l_data.name)
        if existing:
            existing_val = round(existing.Elevation / l_mult, 1)
            levels_to_update.append(f"• {l_data.name} [ID: {l_data.id}] ({existing_val} -> {display_elevation} {l_unit})")
        else:
            levels_to_create.append(f"• {l_data.name} [ID: {l_data.id}] ({display_elevation} {l_unit})")

    # Process Grids
    for g_data in p_data.grids:
        existing = grid_mgr._grid_cache.get(g_data.id) or grid_mgr._grid_cache.get(g_data.name)
        if existing:
            grids_to_update.append(f"• Grid {g_data.name} [ID: {g_data.id}]")
        else:
            grids_to_create.append(f"• Grid {g_data.name} [ID: {g_data.id}]")

    report = "AI AGENT TRANSACTION PREVIEW\n"
    report += "==================================\n\n"
    report += f"Coordinate Origin: {p_data.settings.coordinate_system.upper()}\n"
    report += f"Unit Profiles:     Levels: {l_unit.upper()} | Grids: {g_unit.upper()}\n\n"
    
    report += f"LEVEL CHANGES ({len(levels_to_create)} New, {len(levels_to_update)} Update):\n"
    for item in levels_to_create: report += f"  [+] Create {item}\n"
    for item in levels_to_update: report += f"  [*] Update {item}\n"
    
    report += f"\nGRID CHANGES ({len(grids_to_create)} New, {len(grids_to_update)} Update):\n"
    for item in grids_to_create: report += f"  [+] Create {item}\n"
    for item in grids_to_update: report += f"  [*] Update {item}\n"
    
    return report

def show_preview_dialog(report_text: str) -> bool:
    """Prompt confirm dialog box using corrected UI namespace."""
    dialog = UI.TaskDialog("AI Revit Agent Preview")
    dialog.MainInstruction = "Do you want to apply these model changes?"
    dialog.MainContent = report_text
    dialog.CommonButtons = UI.TaskDialogCommonButtons.Yes | UI.TaskDialogCommonButtons.No
    dialog.DefaultButton = UI.TaskDialogResult.Yes
    
    result = dialog.Show()
    return result == UI.TaskDialogResult.Yes

def main():
    print("🚀 Initializing BIM AI Agent...")
    try:
        payload = PayloadManager(AI_JSON_PAYLOAD)
        p_data = payload.project_data
    except Exception as e:
        print(f"❌ Invalid AI Data: {e}")
        return

    # Initialize Coordinate Utility
    coord_util = CoordinateUtility(doc, p_data.settings.coordinate_system)
    
    level_mgr = LevelManager(doc, coord_util)
    grid_mgr = GridManager(doc, coord_util)

    # 1. Run Analysis and Generate Dry-Run Preview report
    report = generate_dry_run_report(p_data, level_mgr, grid_mgr)
    
    # 2. Present Confirmation Dialog
    if not show_preview_dialog(report):
        print("⚠️ Transaction aborted by user.")
        return

    # 3. Open Transaction to Write Changes
    t = DB.Transaction(doc, "AI Agent: Generate Structure")
    t.Start()
    
    try:
        print("\n🏗️ Processing Levels...")
        for lvl_data in p_data.levels:
            level_mgr.process_from_payload(lvl_data)

        print("\n📐 Processing Grids...")
        for grid_data in p_data.grids:
            grid_mgr.process_from_payload(grid_data)

        # --- THE EXTENTS COORDINATION SEQUENCE ---
        # Regenerate to calculate the base structural coordinates
        doc.Regenerate() 
        
        all_levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
        all_grids = DB.FilteredElementCollector(doc).OfClass(DB.Grid).ToElements()
        
        # Step 1: Maximize Grids vertically first.
        # This forces the grid planes to cross every level from bottom to top.
        print("\n📏 Aligning Grid Vertical Extents...")
        for grid in all_grids:
            grid.Maximize3DExtents()

        # Regenerate again so Revit registers the new, tall 3D grid column bounds
        doc.Regenerate() 

        # Step 2: Maximize Levels. 
        # Since the grids now span all levels, Revit will snap the level lines
        # perfectly to the horizontal limits of the grids!
        print("📏 Aligning Level Horizontal Extents...")
        for lvl in all_levels:
            lvl.Maximize3DExtents()

        t.Commit()
        print("\n🎉 Model Generation Complete!")
        
    except Exception as e:
        t.RollBack()
        print(f"\n💥 FATAL REVIT ERROR: Transaction Rolled Back.\n{e}")

if __name__ == "__main__":
    main()