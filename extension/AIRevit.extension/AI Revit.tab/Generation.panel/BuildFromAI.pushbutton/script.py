#! python3
# -*- coding: utf-8 -*-
"""
Title:       Build From AI
Author:      BIM Manager
Description: Dynamic entrypoint for the structural AI pipeline setup with Hot-Reload.
"""

import os
import sys
import importlib

# Locate the project root dynamically by searching upwards for the 'airevitlib' package
current_dir = os.path.dirname(__file__)
project_root = current_dir

while project_root:
    if os.path.exists(os.path.join(project_root, "airevitlib")):
        break
    parent = os.path.dirname(project_root)
    if parent == project_root:  # Reached the drive root
        project_root = current_dir  # Fallback to local
        break
    project_root = parent

lib_path = os.path.join(project_root, "airevitlib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

# Import all custom library modules first
import core.models
import core.config
import services.ai
import services.compiler
import services.auditor
import revit.coordinates
import revit.elements
import ui.forms
import core.orchestrator

# Force dynamic hot-reloading of all files from disk on every single button click
importlib.reload(core.models)
importlib.reload(core.config)
importlib.reload(services.ai)
importlib.reload(services.compiler)
importlib.reload(services.auditor)
importlib.reload(revit.coordinates)
importlib.reload(revit.elements)
importlib.reload(ui.forms)
importlib.reload(core.orchestrator)

from core.orchestrator import StructuralBIMAgentOrchestrator

# Active Document reference
doc = __revit__.ActiveUIDocument.Document

def main():
    agent = StructuralBIMAgentOrchestrator(doc, project_root)
    agent.run_pipeline()

if __name__ == "__main__":
    main()