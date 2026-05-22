#! python3
# -*- coding: utf-8 -*-
__title__ = 'Build\nFrom AI'
__author__ = 'BIM Manager'

import os
import sys
import json
import importlib
from System.Windows.Forms import DialogResult
import Autodesk.Revit.DB as DB

# Resolve project directories
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, "../../../../../"))
lib_root = os.path.join(project_root, "airevitlib")

# Inject all subfolders directly into search paths to support reliable flat imports
subfolders = [
    lib_root,
    os.path.join(lib_root, "core"),
    os.path.join(lib_root, "services"),
    os.path.join(lib_root, "ui"),
    os.path.join(lib_root, "revit")
]

for folder in subfolders:
    if folder not in sys.path:
        sys.path.insert(0, folder)

# Import custom services directly (Flat Style)
import ui_helper
import ai_interface
import payload_compiler
import payload_manager
import report_generator
import coordinate_utility
import level_manager
import grid_manager

# Force reload of flat modules to bypass pyRevit cache
importlib.reload(ui_helper)
importlib.reload(ai_interface)
importlib.reload(payload_compiler)
importlib.reload(payload_manager)
importlib.reload(report_generator)
importlib.reload(coordinate_utility)
importlib.reload(level_manager)
importlib.reload(grid_manager)

from ui_helper import BIMInputDialog, BIMMessageService
from ai_interface import GeminiClient
from payload_compiler import PayloadCompiler
from payload_manager import PayloadManager
from report_generator import DryRunReportService
from coordinate_utility import CoordinateUtility
from level_manager import LevelManager
from grid_manager import GridManager

doc = __revit__.ActiveUIDocument.Document

def main():
    print("🚀 Initializing BIM AI Agent...")
    default_text = (
        "We have a new project named 'District 9 Lab'.\n"
        "We need 1 basement level 4 meters below ground (-4000).\n"
        "The Ground Floor (Level 0) is at 0.\n"
        "Then we need 4 office levels, each exactly 3.8 meters above the previous.\n"
        "Finally, we want a Roof level 4.2 meters above the top floor.\n"
        "All elevations and grids are in mm.\n"
        "Grids along X: three bays of 6000mm, labeled 1, 2, 3, 4.\n"
        "Grids along Y: four bays of 7500mm, labeled A, B, C, D, E.\n"
        "Our coordination point is the project_base_point."
    )

    form = BIMInputDialog(default_text)
    if form.ShowDialog() != DialogResult.OK:
        print("⚠️ Execution canceled.")
        return

    user_brief = form.textbox.Text.strip()
    if not user_brief:
        BIMMessageService.show_error("The design brief input was empty.")
        return

    print("\n🤖 Sending request to Gemini...")
    try:
        api_key = os.environ.get("GEMINI_API_KEY", "AIzaSyCxZW8zex0P3TnvApNnLLwG5_pR4yMcusI")
        client = GeminiClient(api_key=api_key)
        intent_data = client.query_intent(user_brief)
    except Exception as api_err:
        BIMMessageService.show_error("AI Engine error:\n\n{}".format(api_err))
        return

    try:
        compiler = PayloadCompiler(intent_data, grid_offset_buffer=5000.0)
        compiled_payload = compiler.compile()
        payload_path = os.path.join(project_root, "payload.json")
        with open(payload_path, "w") as f:
            json.dump(compiled_payload, f, indent=4)
        
        payload_mgr = PayloadManager(json.dumps(compiled_payload))
        p_data = payload_mgr.project_data
    except Exception as comp_err:
        BIMMessageService.show_error("Geometry compilation error:\n\n{}".format(comp_err))
        return

    coord_util = CoordinateUtility(doc, p_data.settings.coordinate_system)
    level_mgr = LevelManager(doc, coord_util)
    grid_mgr = GridManager(doc, coord_util)

    report_text = DryRunReportService.generate_report(p_data, level_mgr, grid_mgr)
    if not BIMMessageService.show_preview(report_text):
        print("⚠️ Transaction aborted.")
        return

    t = DB.Transaction(doc, "AI Agent: Generate Structure")
    t.Start()
    try:
        print("\n🏗️ Processing Levels...")
        for lvl_data in p_data.levels:
            level_mgr.process_from_payload(lvl_data)

        print("\n📐 Processing Grids...")
        for grid_data in p_data.grids:
            grid_mgr.process_from_payload(grid_data)

        doc.Regenerate()
        all_levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
        all_grids = DB.FilteredElementCollector(doc).OfClass(DB.Grid).ToElements()

        print("\n📏 Aligning Grid Vertical Extents...")
        for grid in all_grids: grid.Maximize3DExtents()

        doc.Regenerate()
        print("📏 Aligning Level Horizontal Extents...")
        for lvl in all_levels: lvl.Maximize3DExtents()

        t.Commit()
        print("\n🎉 Model Generation Complete!")
    except Exception as e:
        t.RollBack()
        BIMMessageService.show_error("Failed to execute Revit modeling transaction.\n\n{}".format(e))

if __name__ == "__main__":
    main()