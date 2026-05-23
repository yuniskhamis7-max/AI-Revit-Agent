# airevitlib/core/orchestrator.py
import os
import json
import random
import Autodesk.Revit.DB as DB
import System.Windows.Forms as WinForms
from ui.forms import BIMConversationalDashboard, BIMMessageService
from core.config import ConfigManager
from services.ai import GeminiClient
from services.compiler import DirectUnitCompiler
from revit.coordinates import CoordinateUtility
from revit.elements import StructuralManager

class StructuralBIMAgentOrchestrator:
    """Manages the verification loop and coordinates the database transaction updates."""

    def __init__(self, doc: DB.Document, project_root_path: str):
        self.doc = doc
        self.root = project_root_path
        self.chat_history = []  # Conversational memory buffer starts completely empty
        self.model_context = None

    def run_pipeline(self):
        cfg = ConfigManager(self.root)
        saved_cfg = cfg.load_config()

        # Extract actual Revit database state once. It remains static during the chat loop.
        coord_util = CoordinateUtility(self.doc, "project_base_point")
        self.manager = StructuralManager(self.doc, coord_util)
        self.model_context = self.manager.get_existing_model_context()

        # Initialize the Conversational Verification loop UI (No default template inputs)
        form = BIMConversationalDashboard(
            saved_key=saved_cfg["api_key"],
            saved_model=saved_cfg["selected_model"],
            fetch_models_func=GeminiClient.fetch_available_models,
            on_query_callback=self._process_conversational_query
        )

        # Show conversational dialog panel and monitor response
        if form.ShowDialog() != WinForms.DialogResult.OK:
            print("Layout operation cancelled.")
            return
        
        # Retrieve the validated payload
        validated_data = form.validated_payload
        if not validated_data:
            return

        # Phase 5: Run Database Transaction with clean derived geometry calculations
        # We pass self.model_context so the compiler can self-heal and stretch preserved grids
        compiler = DirectUnitCompiler(validated_data, self.model_context)
        compiled_data = compiler.compile()

        t = DB.Transaction(self.doc, "AI Agent: Conversational Structural Setup")
        t.Start()
        try:
            # Phase 1: Full-State Synchronization & Duplicate Sweep
            print("Synchronizing model state and preparing deletions...")
            
            # Map compiled active keys
            active_level_keys = set()
            for l in compiled_data.levels:
                active_level_keys.add(l.id)
                active_level_keys.add(l.name)

            active_grid_keys = set()
            for g in compiled_data.grids:
                active_grid_keys.add(g.id)
                active_grid_keys.add(g.name)

            # Match exactly one element per active name, flag all duplicates and leftover elements for deletion
            matched_level_names = set()
            to_delete_levels = []
            
            # Safe Fail-Safe: Only perform level deletions if our compiled active set contains at least one level
            if compiled_data.levels:
                all_levels = DB.FilteredElementCollector(self.doc) \
                    .OfClass(DB.Level) \
                    .WhereElementIsNotElementType() \
                    .ToElements()
                    
                for lvl in all_levels:
                    if not lvl.IsValidObject:
                        continue
                    tracking_id = self.manager._get_tracking_id(lvl, self.manager.LVL_PREFIX)
                    name = lvl.Name
                    
                    if (tracking_id in active_level_keys or name in active_level_keys) and name not in matched_level_names:
                        matched_level_names.add(name)
                    else:
                        # Rename immediately to free up name and flag for deletion
                        try:
                            lvl.Pinned = False
                            lvl.Name = "ToDelete_level_{}".format(random.randint(10000, 99999))
                        except Exception as ex:
                            print("Warning: Could not rename duplicate level: {}".format(ex))
                        to_delete_levels.append(lvl)
            else:
                print("Warning: Compiled levels list is empty. Aborting levels cleanup to prevent complete model wipe.")

            matched_grid_names = set()
            to_delete_grids = []
            
            # Safe Fail-Safe: Only perform grid deletions if our compiled active set contains at least one grid
            if compiled_data.grids:
                all_grids = DB.FilteredElementCollector(self.doc) \
                    .OfClass(DB.Grid) \
                    .WhereElementIsNotElementType() \
                    .ToElements()
                    
                for grd in all_grids:
                    if not grd.IsValidObject:
                        continue
                    tracking_id = self.manager._get_tracking_id(grd, self.manager.GRD_PREFIX)
                    name = grd.Name
                    
                    if (tracking_id in active_grid_keys or name in active_grid_keys) and name not in matched_grid_names:
                        matched_grid_names.add(name)
                    else:
                        # Rename immediately to free up name and flag for deletion
                        try:
                            grd.Pinned = False
                            grd.Name = "ToDelete_grid_{}".format(random.randint(10000, 99999))
                        except Exception as ex:
                            print("Warning: Could not rename duplicate grid: {}".format(ex))
                        to_delete_grids.append(grd)
            else:
                print("Warning: Compiled grids list is empty. Aborting grids cleanup to prevent complete model wipe.")

            # Pop the elements flagged for deletion out of active manager caches
            for lvl in to_delete_levels:
                self.manager._levels.pop(lvl.Name, None)
            for grd in to_delete_grids:
                self.manager._grids.pop(grd.Name, None)

            # Phase 2: Process creations and updates for levels
            print("Processing levels...")
            base_z = 0.0
            for lvl_dto in compiled_data.levels:
                self.manager.process_level(lvl_dto)
                if lvl_dto.elevation < base_z:
                    base_z = lvl_dto.elevation

            # Phase 3: Process creations and updates for grids (including self-healed preserved grids)
            print("Processing grids using footprint boundaries...")
            for grid_dto in compiled_data.grids:
                self.manager.process_grid(grid_dto, base_z)

            # Phase 4: Execute final deletions of renamed and decoupled items
            print("\nExecuting deletions...")
            self.manager.execute_deletions(to_delete_levels)
            self.manager.execute_deletions(to_delete_grids)

            # Phase 5: Regenerate document to clear old geometry from bounding box checks
            self.doc.Regenerate()

            # Phase 6: Maximize level and grid extents to neatly match all active boundaries
            # This vertical and horizontal optimization step ensures both grids and levels intersect cleanly.
            print("Optimizing visual level and grid extents...")
            active_levels = DB.FilteredElementCollector(self.doc) \
                .OfClass(DB.Level) \
                .WhereElementIsNotElementType() \
                .ToElements()

            for lvl in active_levels:
                try:
                    lvl.Maximize3DExtents()
                except Exception as ex:
                    print("Warning: Could not optimize 3D extents for level '{}': {}".format(lvl.Name, ex))

            active_grids = DB.FilteredElementCollector(self.doc) \
                .OfClass(DB.Grid) \
                .WhereElementIsNotElementType() \
                .ToElements()

            for grd in active_grids:
                try:
                    grd.Maximize3DExtents()
                except Exception as ex:
                    print("Warning: Could not optimize 3D extents for grid '{}': {}".format(grd.Name, ex))

            self.doc.Regenerate()
            t.Commit()
            print("\nBIM Elements synchronized successfully.")
        except Exception as err:
            t.RollBack()
            BIMMessageService.show_error(f"Transaction aborted:\n\n{err}")

    def _process_conversational_query(self, user_prompt: str, api_key: str, model_name: str) -> dict:
        """Callback to query the AI client, matching changes against the static, true Revit database state."""
        # 1. Append the user's latest input to the chronological memory
        self.chat_history.append({"role": "user", "text": user_prompt})

        client = GeminiClient(api_key=api_key, model_name=model_name)
        
        # 2. Pass cumulative conversation history + static true Revit model state (not proposed states) to the AI
        ai_response = client.query_intent(self.chat_history, self.model_context)
        
        # 3. Append the AI's response to the chronological memory
        clarification = ai_response.get("clarification_message", "")
        self.chat_history.append({"role": "model", "text": clarification})
        
        return ai_response