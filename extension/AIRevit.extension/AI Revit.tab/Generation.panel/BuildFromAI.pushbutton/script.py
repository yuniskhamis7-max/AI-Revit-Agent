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

# Setup project library search paths
current_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(current_dir, "../../../../../"))
lib_root = os.path.join(project_root, "airevitlib")

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

# Import custom modules directly (Flat Style)
import ui_helper
import ai_interface
import config_manager
import payload_compiler
import payload_manager
import report_generator
import coordinate_utility
import level_manager
import grid_manager

# Force reload modules to prevent assembly caching issues
importlib.reload(ui_helper)
importlib.reload(ai_interface)
importlib.reload(config_manager)
importlib.reload(payload_compiler)
importlib.reload(payload_manager)
importlib.reload(report_generator)
importlib.reload(coordinate_utility)
importlib.reload(level_manager)
importlib.reload(grid_manager)

from ui_helper import BIMInputDialog, BIMMessageService
from ai_interface import GeminiClient
from config_manager import ConfigManager
from payload_compiler import PayloadCompiler
from payload_manager import PayloadManager
from report_generator import DryRunReportService
from coordinate_utility import CoordinateUtility
from level_manager import LevelManager
from grid_manager import GridManager

doc = __revit__.ActiveUIDocument.Document

def main():
    print("🚀 Initializing BIM AI Agent...")
    
    # 1. Load active project configuration
    cfg = ConfigManager(project_root)
    saved_cfg = cfg.load_config()

    default_text = (
        "مذكرة تصميمية مبدئية: \"مركز غزة الطبي\".\n"
        "الأرضي عند الصفر بالطبع.\n"
        "الطابق الأول على منسوب 4200 مم.\n"
        "الطابق الثاني على منسوب 8400 مم.\n"
        "القبو الأول (B1) يجب أن يكون تحت الأرض بـ 3600 مم.\n"
        "السطح (Roof) عند 12600 مم.\n"
        "المحاور:\n"
        "محاور X: نريد 4 مجازات (bays) بمسافة 6 أمتار لكل منها (من 1 إلى 5).\n"
        "محاور Y: لم تكتمل دراسة الموقع بعد! لكن مبدئياً ضعوا 3 مجازات نموذجية بمسافة 7.2 متر لكل منها وسنعدلها لاحقاً بعد موافقة المعماري الأساسي.\n"
        "سنربط الإحداثيات بنقطة المساحة المشتركة للموقع (survey_point). الوحدات ملم."
    )

    # 2. Show Unified Dashboard UI passing credentials and the dynamic model-fetch callback
    form = BIMInputDialog(
        default_text=default_text,
        saved_key=saved_cfg["api_key"],
        saved_model=saved_cfg["selected_model"],
        fetch_models_func=GeminiClient.fetch_available_models
    )
    
    if form.ShowDialog() != DialogResult.OK:
        print("⚠️ Execution canceled.")
        return

    # 3. Retrieve form choices securely using Python native typing
    user_api_key = form.txt_api.Text.strip()
    user_brief = form.txt_brief.Text.strip()
    user_model = "gemini-2.5-flash"  # Standard default fallback
    
    if form.cmb_models.SelectedItem:
        user_model = str(form.cmb_models.SelectedItem)

    if not user_api_key:
        BIMMessageService.show_error("Gemini API Key is required to run the AI Agent.")
        return
        
    if not user_brief:
        BIMMessageService.show_error("The design brief input was empty.")
        return

    # 4. Save any updated credentials/selections back to your git-ignored config file
    cfg.save_config(user_api_key, user_model)

    print("\n🤖 Sending request to Gemini (Model: {})...".format(user_model))
    try:
        client = GeminiClient(api_key=user_api_key, model_name=user_model)
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