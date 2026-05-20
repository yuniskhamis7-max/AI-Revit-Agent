#! python3
# -*- coding: utf-8 -*-
"""
Build From AI
Generates Revit Grids and Levels based on AI JSON Payload.
"""
__title__ = 'Build\nFrom AI'
__author__ = 'BIM Manager'

import Autodesk.Revit.DB as DB

import Autodesk.Revit.DB as DB
import os
import sys


# Dynamically resolve the path to the 'lib' directory
current_dir = os.path.dirname(__file__)
lib_path = os.path.abspath(os.path.join(current_dir, "../../../../../lib"))
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)



from dtos import ProjectData
from payload_manager import PayloadManager
from revit_managers.level_manager import LevelManager
from revit_managers.grid_manager import GridManager

doc = __revit__.ActiveUIDocument.Document

# Simulated AI Payload
AI_JSON_PAYLOAD = """
{
    "levels": [
        {"name": "B1 - Parking", "elevation": -12.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L0 - Ground Floor", "elevation": 0.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L1 - Offices", "elevation": 14.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L2 - Offices", "elevation": 28.0, "is_pinned": true, "create_floor_plan": true},
        {"name": "L3 - Roof", "elevation": 42.0, "is_pinned": false, "create_floor_plan": false}
    ],
    "grids": [
        {"name": "A", "start": {"x": -5.0, "y": 0.0}, "end": {"x": 105.0, "y": 0.0}, "is_pinned": true},
        {"name": "B", "start": {"x": -5.0, "y": 30.0}, "end": {"x": 105.0, "y": 30.0}, "is_pinned": true},
        {"name": "C", "start": {"x": -5.0, "y": 60.0}, "end": {"x": 105.0, "y": 60.0}, "is_pinned": true},
        {"name": "D", "start": {"x": -5.0, "y": 90.0}, "end": {"x": 105.0, "y": 90.0}, "is_pinned": true},
        {"name": "1", "start": {"x": 0.0, "y": -5.0}, "end": {"x": 0.0, "y": 95.0}, "is_pinned": true},
        {"name": "2", "start": {"x": 30.0, "y": -5.0}, "end": {"x": 30.0, "y": 95.0}, "is_pinned": true},
        {"name": "3", "start": {"x": 60.0, "y": -5.0}, "end": {"x": 60.0, "y": 95.0}, "is_pinned": true},
        {"name": "4", "start": {"x": 100.0, "y": -5.0}, "end": {"x": 100.0, "y": 95.0}, "is_pinned": true}
    ]
}
"""

def main():
    print("🚀 Initializing AI-Revit Agent...")

    # 1. Parse and Validate
    try:
        payload = PayloadManager(AI_JSON_PAYLOAD)
        print("✅ AI Payload successfully parsed and validated.")
    except Exception as e:
        print("❌ FAILED: AI provided invalid data. " + str(e))
        return

    # 2. Initialize Managers
    level_mgr = LevelManager(doc)
    grid_mgr = GridManager(doc)

    # 3. Execute Built Operation inside a standard Revit Transaction
    t = DB.Transaction(doc, "AI Agent: Generate Structure")
    t.Start()
    
    try:
        print("\n🏗️ Building Levels...")
        for lvl_data in payload.get_levels():
            level = level_mgr.process_from_payload(lvl_data)
            status = "Created/Updated" if level else "Failed"
            print("  -> {} Level: {} (Elev: {})".format(status, lvl_data.name, lvl_data.elevation))

        print("\n📐 Building Grids...")
        for grid_data in payload.get_grids():
            grid = grid_mgr.process_from_payload(grid_data)
            status = "Created/Verified" if grid else "Skipped/Failed"
            print("  -> {} Grid: {}".format(status, grid_data.name))

        # If everything succeeded, commit to the Revit file
        t.Commit()
        print("\n🎉 AI Generation Complete!")
        
    except Exception as e:
        # If ANY Revit API crash happens midway, undo everything!
        t.RollBack()
        print("\n💥 FATAL REVIT ERROR: Transaction Rolled Back to protect model.")
        print(str(e))

if __name__ == "__main__":
    main()