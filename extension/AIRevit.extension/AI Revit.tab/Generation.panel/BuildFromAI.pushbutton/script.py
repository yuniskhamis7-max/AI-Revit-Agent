#! python3
# -*- coding: utf-8 -*-
__title__ = 'Build\nFrom AI'
__author__ = 'BIM Manager'

import Autodesk.Revit.DB as DB
import os
import sys
import importlib

current_dir = os.path.dirname(__file__)
lib_path = os.path.abspath(os.path.join(current_dir, "../../../../../lib"))
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

import dtos
import payload_manager
import revit_managers.level_manager
import revit_managers.grid_manager
import revit_managers.link_manager

# Force Reloads to ensure no pyRevit caching issues
importlib.reload(dtos)
importlib.reload(payload_manager)
importlib.reload(revit_managers.level_manager)
importlib.reload(revit_managers.grid_manager)
importlib.reload(revit_managers.link_manager)

from dtos import ProjectData
from payload_manager import PayloadManager
from revit_managers.level_manager import LevelManager
from revit_managers.grid_manager import GridManager
from revit_managers.link_manager import LinkManager

doc = __revit__.ActiveUIDocument.Document

# Large Scale Real-World Multi-Use Tower Payload
AI_JSON_PAYLOAD = """
{
    "settings": {
        "grids_unit": "mm",
        "levels_unit": "mm",
        "use_project_base_point": true
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
        {"name": "B2 - Foundation Slab", "elevation": -7200.0, "is_pinned": true, "create_floor_plan": false},
        {"name": "B1 - Parking Garage", "elevation": -3600.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L0 - Entrance Lobby (PBP)", "elevation": 0.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L1 - Retail Mezzanine", "elevation": 4800.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L2 - Office Typical 01", "elevation": 9000.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L3 - Office Typical 02", "elevation": 12800.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L4 - Office Typical 03", "elevation": 16600.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L5 - Mechanical & Plant", "elevation": 20400.0, "is_pinned": true, "create_floor_plan": false},
        {"name": "L6 - Residential Amenity", "elevation": 24600.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L7 - Residential Typical 01", "elevation": 27800.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L8 - Residential Typical 02", "elevation": 31000.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L9 - Residential Typical 03", "elevation": 34200.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L10 - Penthouse Suite", "elevation": 37400.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "Roof Deck / Terrace", "elevation": 41200.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "Top of Parapet", "elevation": 42700.0, "is_pinned": false, "create_floor_plan": false}
    ],
    "grids": [
        {"name": "1", "start": {"x": 0.0, "y": -4000.0}, "end": {"x": 0.0, "y": 44000.0}, "is_pinned": true},
        {"name": "2", "start": {"x": 6000.0, "y": -4000.0}, "end": {"x": 6000.0, "y": 44000.0}, "is_pinned": true},
        {"name": "3", "start": {"x": 14000.0, "y": -4000.0}, "end": {"x": 14000.0, "y": 44000.0}, "is_pinned": true},
        {"name": "4", "start": {"x": 22000.0, "y": -4000.0}, "end": {"x": 22000.0, "y": 44000.0}, "is_pinned": true},
        {"name": "5", "start": {"x": 28000.0, "y": -4000.0}, "end": {"x": 28000.0, "y": 44000.0}, "is_pinned": true},
        {"name": "6", "start": {"x": 37000.0, "y": -4000.0}, "end": {"x": 37000.0, "y": 44000.0}, "is_pinned": true},
        {"name": "7", "start": {"x": 46000.0, "y": -4000.0}, "end": {"x": 46000.0, "y": 44000.0}, "is_pinned": true},
        {"name": "8", "start": {"x": 52000.0, "y": -4000.0}, "end": {"x": 52000.0, "y": 44000.0}, "is_pinned": true},
        
        {"name": "A", "start": {"x": -4000.0, "y": 0.0}, "end": {"x": 56000.0, "y": 0.0}, "is_pinned": true},
        {"name": "B", "start": {"x": -4000.0, "y": 7500.0}, "end": {"x": 56000.0, "y": 7500.0}, "is_pinned": true},
        {"name": "C", "start": {"x": -4000.0, "y": 15000.0}, "end": {"x": 56000.0, "y": 15000.0}, "is_pinned": true},
        {"name": "D", "start": {"x": -4000.0, "y": 21000.0}, "end": {"x": 56000.0, "y": 21000.0}, "is_pinned": true},
        {"name": "E", "start": {"x": -4000.0, "y": 29500.0}, "end": {"x": 56000.0, "y": 29500.0}, "is_pinned": true},
        {"name": "F", "start": {"x": -4000.0, "y": 38000.0}, "end": {"x": 56000.0, "y": 38000.0}, "is_pinned": true}
    ]
}
"""

def main():
    print("🚀 Initializing BIM AI Agent...")
    try:
        payload = PayloadManager(AI_JSON_PAYLOAD)
        p_data = payload.project_data
    except Exception as e:
        print(f"❌ Invalid AI Data: {e}")
        return

    use_pbp = p_data.settings.use_project_base_point
    
    level_mgr = LevelManager(doc, use_pbp=use_pbp)
    grid_mgr = GridManager(doc, use_pbp=use_pbp)
    link_mgr = LinkManager(doc)

    t = DB.Transaction(doc, "AI Agent: Generate Structure")
    t.Start()
    
    try:
        print(f"\n🏗️ Processing Levels (Strategy: {p_data.level_strategy.mode})...")
        if p_data.level_strategy.mode == "link" and p_data.level_strategy.link_name:
            print("  -> Copying Levels from Link...")
            link_mgr.copy_levels(p_data.level_strategy.link_name, p_data.level_strategy.prefix_copied_levels)
        else:
            print("  -> Creating explicit Levels...")
            for lvl_data in p_data.levels:
                level_mgr.process_from_payload(lvl_data)

        print(f"\n📐 Processing Grids (Strategy: {p_data.grid_strategy.mode})...")
        if p_data.grid_strategy.mode == "link" and p_data.grid_strategy.link_name:
            print("  -> Copying Grids from Link...")
            link_mgr.copy_grids(p_data.grid_strategy.link_name, p_data.grid_strategy.prefix_copied_grids)
        else:
            print("  -> Drawing explicit Grids...")
            for grid_data in p_data.grids:
                grid_mgr.process_from_payload(grid_data)

        # --- THE EXTENTS FIX ---
        # 1. Regenerate so Revit calculates the new Bounding Box of the drawn grids
        doc.Regenerate() 
        all_levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
        
        # 2. WE ONLY MAXIMIZE LEVELS. 
        # Grids are left alone so they perfectly respect the start/end coordinates of the JSON!
        print("\n📏 Aligning 3D Extents...")
        for lvl in all_levels:
            lvl.Maximize3DExtents()

        t.Commit()
        print("\n🎉 Model Generation Complete!")
        
    except Exception as e:
        t.RollBack()
        print(f"\n💥 FATAL REVIT ERROR: Transaction Rolled Back.\n{e}")

if __name__ == "__main__":
    main()