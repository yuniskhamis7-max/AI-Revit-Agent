# airevitlib/core/orchestrator.py
import os
import json
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
        compiler = DirectUnitCompiler(validated_data)
        compiled_data = compiler.compile()

        t = DB.Transaction(self.doc, "AI Agent: Conversational Structural Setup")
        t.Start()
        try:
            print("\nExecuting deletions...")
            delta = validated_data.get("proposed_delta") or {}
            levels_section = delta.get("levels") or {}
            grids_section = delta.get("grids") or {}

            self.manager.execute_deletions(levels_section.get("delete") or [], "level")
            self.manager.execute_deletions(grids_section.get("delete") or [], "grid")

            print("Processing levels...")
            base_z = 0.0
            for lvl_dto in compiled_data.levels:
                self.manager.process_level(lvl_dto)
                if lvl_dto.elevation < base_z:
                    base_z = lvl_dto.elevation

            print("Processing grids using footprint boundaries...")
            for grid_dto in compiled_data.grids:
                self.manager.process_grid(grid_dto, base_z)

            self.doc.Regenerate()
            t.Commit()
            print("\nBIM Elements synchronized successfully.")
        except Exception as err:
            t.RollBack()
            BIMMessageService.show_error(f"Transaction aborted:\n\n{err}")

    def _process_conversational_query(self, user_prompt: str, api_key: str, model_name: str) -> dict:
        """Callback to query the AI client, matching changes against the static model state with memory."""
        # 1. Append the user's latest input to the chronological memory
        self.chat_history.append({"role": "user", "text": user_prompt})

        client = GeminiClient(api_key=api_key, model_name=model_name)
        
        # 2. Pass the cumulative conversation history + static Revit state to the AI
        ai_response = client.query_intent(self.chat_history, self.model_context)
        
        # 3. Append the AI's response to the chronological memory
        clarification = ai_response.get("clarification_message", "")
        self.chat_history.append({"role": "model", "text": clarification})
        
        # 4. Safely update our in-memory cache of the conversation context
        delta = ai_response.get("proposed_delta") or {}
        levels_section = delta.get("levels") or {}
        grids_section = delta.get("grids") or {}

        lvl_create = levels_section.get("create") or []
        lvl_update = levels_section.get("update") or []
        grd_create = grids_section.get("create") or []
        grd_update = grids_section.get("update") or []

        self.model_context = {
            "levels": lvl_create + lvl_update,
            "grids": grd_create + grd_update
        }
        return ai_response