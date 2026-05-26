#! python3
# -*- coding: utf-8 -*-
"""
Title:       Build From AI
Author:      BIM Manager
Description: Dynamic entrypoint with hot-reloads, console debugging prints, 
             and contextual model synchronization.
"""

import os
import sys
import json
import importlib

# 1. Dynamically locate project root by searching upwards for the 'airevitlib' directory
current_dir = os.path.dirname(__file__)
project_root = current_dir

while project_root:
    if os.path.exists(os.path.join(project_root, "airevitlib")):
        break
    parent = os.path.dirname(project_root)
    if parent == project_root:  # Reached the drive root (fallback configuration)
        project_root = current_dir
        break
    project_root = parent

# 2. Extract path to airevitlib and append directly to system paths
lib_path = os.path.join(project_root, "airevitlib")
if lib_path not in sys.path:
    sys.path.insert(0, lib_path)

# ==============================================================================
# FORCE DYNAMIC HOT-RELOAD OF ALL CUSTOM MODULES BEFORE EXECUTING
# ==============================================================================
import inputprocessing.agents
import inputprocessing.forms
import Revitcreation.categoriesclasses

importlib.reload(inputprocessing.agents)
importlib.reload(inputprocessing.forms)
importlib.reload(Revitcreation.categoriesclasses)
# ==============================================================================

# Now import the freshly reloaded modules into the entrypoint namespace safely
from inputprocessing.agents import BIMAgent, ORGANIZER_SYSTEM_INSTRUCTION, FORMATTER_SYSTEM_INSTRUCTION
from inputprocessing.forms import BIMDoubleApprovalForm
from Revitcreation.categoriesclasses import BIMExecutionEngine

doc = __revit__.ActiveUIDocument.Document

# Dynamic Configuration Loader
def load_configuration():
    api_key = ""
    model_name = "gemini-flash-lite-latest"
    
    config_path = os.path.join(project_root, "airevit_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                api_key = data.get("api_key", "").strip()
                model_name = data.get("selected_model", "gemini-flash-lite-latest").strip()
        except Exception as ex:
            print("Warning: Failed to parse configuration file: {}".format(ex))
            
    # Fallback to environment variables if JSON config is missing or empty
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
        
    return api_key, model_name

# Global elements dictionary (Populated dynamically on startup)
Existing_Elements = {}

def main():
    global Existing_Elements
    
    # Load configuration parameters
    api_key, model_name = load_configuration()
    
    if not api_key:
        print("Required API key is not configured. Please supply your credentials in 'airevit_config.json' or set the GEMINI_API_KEY environment variable.")
        return

    # Initialize Phase 2 Execution Engine
    engine = BIMExecutionEngine(doc)
    
    # Load physical elements directly from active Revit Document on startup
    print("Scanning active Revit model context...")
    Existing_Elements = engine.load_current_state()
    print("Scan complete. Loaded {} levels, {} grids, {} columns, {} foundations.".format(
        len(Existing_Elements["levels"]),
        len(Existing_Elements["grids"]),
        len(Existing_Elements["columns"]),
        len(Existing_Elements["foundations"])
    ))

    # Initialize Conversational Agent layers with configuration settings
    organizer = BIMAgent(api_key, "Organizer", ORGANIZER_SYSTEM_INSTRUCTION, model_name)
    formatter = BIMAgent(api_key, "Formatter", FORMATTER_SYSTEM_INSTRUCTION, model_name)

    # Callback 1: Check request against current live context and dialogue history
    def run_organizer_agent(user_prompt, chat_history):
        context = {
            "existing_elements": Existing_Elements,
            "chat_history": chat_history
        }
        
        # Execute Query
        res_json = organizer.query(user_prompt, context)
        
        # --- DEBUG CONSOLE PRINT ---
        print("\n" + "="*60)
        print("DEBUG: ORGANIZER AGENT RAW OUTPUT")
        print("="*60)
        print(json.dumps(res_json, indent=4))
        print("="*60 + "\n")
        
        return res_json

    # Callback 2: Parse plan items into structural commands (with active context resolution)
    def run_formatter_agent(approved_plan_data):
        context = {
            "existing_elements": Existing_Elements
        }
        
        # Execute Query passing both plan and active element state
        res_json = formatter.query(str(approved_plan_data), context)
        
        # --- DEBUG CONSOLE PRINT ---
        print("\n" + "="*60)
        print("DEBUG: FORMATTER AGENT RAW OUTPUT")
        print("="*60)
        print(json.dumps(res_json, indent=4))
        print("="*60 + "\n")
        
        return res_json

    # Launch conversational verification workspace panel
    form = BIMDoubleApprovalForm(Existing_Elements, run_organizer_agent, run_formatter_agent)
    
    import System.Windows.Forms as WinForms
    if form.ShowDialog() == WinForms.DialogResult.OK:
        staged_commands = form.approved_commands
        if staged_commands:
            print("Applying transaction commands to Revit...")
            success = engine.execute_transaction(staged_commands)
            
            if success:
                print("Transaction complete. Updating local tracking context...")
                Existing_Elements = engine.load_current_state()
                print("Synchronization complete. Staged elements are now live.")
            else:
                print("Failed to apply commands. Transaction was rolled back.")

if __name__ == "__main__":
    main()