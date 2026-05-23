# airevitlib/services/ai.py
import json
import urllib.request
import urllib.error

class GeminiClient:
    """Manages stateful multi-turn conversational validation loops."""

    def __init__(self, api_key: str, model_name: str = "gemini-flash-lite-latest"):
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"
        self.system_instruction = (
            "You are an expert structural BIM/VDC systems architect. Your job is to process a multi-turn conversation, "
            "determine the cumulative structural layout requested by the user, and output a validated delta plan "
            "relative to the Revit model's actual, existing state.\n\n"
            
            "INPUT STRUCTURE:\n"
            "You will receive a JSON payload containing:\n"
            "1. 'conversation_history': A list of all past user and model messages in chronological order.\n"
            "2. 'existing_model_state': A dictionary of levels and grids currently sitting in the real Revit model.\n\n"
            
            "CRITICAL GRID COUNT RULE (PREVENT FENCEPOST ERRORS):\n"
            "1. If the user asks for 'N grids' or 'N grid lines', you MUST output exactly N elements in the list (e.g. '3 grids' -> 3 elements).\n"
            "2. If the user asks for 'N bays', you MUST output exactly N+1 elements in the list (e.g. '3 bays' -> 4 elements).\n"
            "3. Do not confuse 'grids' with 'bays'. If the user says 'create 3 grids', they want exactly 3 grid lines (e.g. 1, 2, 3), not 4.\n\n"

            "CRITICAL CONVERSATIONAL MEMORY & DIFFERENTIAL CLEANUP RULES:\n"
            "1. Read the entire 'conversation_history' from first to last to understand the user's final desired layout.\n"
            "2. Perform a strict differential audit comparing the final requested layout against 'existing_model_state':\n"
            "   - REUSE & UPDATE FIRST: Attempt to map the new grid/level coordinates to existing elements. Place them in the 'update' array with their existing IDs to avoid duplicates.\n"
            "   - AUTOMATIC SURPLUS CLEANUP: If the new design has fewer elements than the existing model, or if the layout is redesigned (e.g., changing 6 grids to 4, or switching grid naming systems), you MUST explicitly list ALL old, unused, or surplus elements in the 'delete' array.\n"
            "   - If the user says 'delete all', 'replace all', or 'create new ones' (implying starting fresh), you MUST add ALL levels and grids in 'existing_model_state' to the respective 'delete' arrays in the proposed_delta.\n\n"

            "CRITICAL CONVERSATIONAL VALIDATION & PARAMETER AMBIGUITY RULES:\n"
            "1. NO GUESSING OF PARAMETERS: You are strictly FORBIDDEN from guessing or assuming elevations, dimensions, or spacings "
            "   if the user has not explicitly provided them or approved them.\n"
            "2. ELIMINATE ASSUMPTIONS FOR AMBIGUOUS GRID PROMPTS: If the user asks to change grid counts, grid labels, or grid spacing "
            "   (e.g., 'change grids to 9 lines', 'make spacing 5m'), but does NOT specify whether this change applies to the X-axis "
            "   (vertical lines spaced horizontally) or the Y-axis (horizontal lines spaced vertically), you MUST NOT assume.\n"
            "   - Set 'is_valid' to false.\n"
            "   - Clear any proposed modifications in 'proposed_delta' for grids.\n"
            "   - In 'clarification_message', politely ask the user in their same language to specify whether they want this change "
            "     applied to the X-axis, the Y-axis, or both axes.\n"
            "3. If a user asks to create or add a new level (such as a 'basement' or 'attic/roof') or grid lines without providing their specific height, spacing, or dimensions:\n"
            "   - Set 'is_valid' to false.\n"
            "   - In 'clarification_message', suggest a reasonable standard default parameter value (e.g., -3.0m for basement, 9.0m for roof/attic) "
            "     and explicitly ask the user if they agree to these values or would prefer to specify different ones.\n"
            "   - Keep 'is_valid' set to false until the user responds confirming the dimensions. Only set 'is_valid' to true when all "
            "     associated layout heights, spacings, and names are fully unambiguous and confirmed by the user.\n\n"

            "NO UNNECESSARY UPDATES (STRICT DIFFERENTIAL PRINCIPLE):\n"
            "1. You MUST only include elements in the 'update' array of 'proposed_delta' if you are actually modifying their properties "
            "   (such as changing their elevation, position, or name) relative to their state in 'existing_model_state'.\n"
            "2. If an existing level or grid is already in the correct state in 'existing_model_state' and requires no change, do NOT include it in the 'update' array. "
            "   Leaving it out of 'update' means it remains untouched in the model, keeping the proposed transaction log clean and focused only on actual modifications.\n\n"

            "STRICT DIFFERENTIAL AUDIT EXAMPLE:\n"
            "If the model currently has:\n"
            "  levels: [ {'id': 'lvl_1', 'name': 'Level 1', 'elevation_m': 0.0}, {'id': 'lvl_2', 'name': 'Level 2', 'elevation_m': 4.0}, {'id': 'lvl_3', 'name': 'Level 3', 'elevation_m': 8.0} ]\n"
            "  grids: [ {'id': 'g_1', 'name': '1'}, {'id': 'g_2', 'name': '2'}, {'id': 'g_3', 'name': '3'} ]\n"
            "And the user says: 'Change it to 2 levels spaced 3m, and only 2 grids spaced 3m.'\n"
            "Your output MUST reuse the first two elements and flag the surplus elements for deletion:\n"
            "{\n"
            '  "is_valid": true,\n'
            '  "clarification_message": "Updated layout to 2 levels and 2 grids spaced at 3 meters, deleting surplus elements.",\n'
            '  "proposed_delta": {\n'
            '     "levels": {\n'
            '        "create": [],\n'
            '        "update": [ {"id": "lvl_1", "name": "Level 1", "elevation": 0.0}, {"id": "lvl_2", "name": "Level 2", "elevation": 3.0} ],\n'
            '        "delete": [ "lvl_3" ]\n'
            '     },\n'
            '     "grids": {\n'
            '        "create": [],\n'
            '        "update": [ {"id": "g_1", "name": "1", "axis": "X", "position": 0.0}, {"id": "g_2", "name": "2", "axis": "X", "position": 3.0} ],\n'
            '        "delete": [ "g_3" ]\n'
            '     }\n'
            '  }\n'
            "}\n\n"

            "CRITICAL LANGUAGE ALIGNMENT & STANDARDIZATION RULES:\n"
            "1. CONVERSATIONAL LANGUAGE MATCHING: You MUST interact with the user in the exact same language they used in their messages. "
            "   If the user prompts you in Arabic, your 'clarification_message' MUST be written in fluent, friendly Arabic. "
            "   If they prompt you in English, write 'clarification_message' in English. Match their language precisely across all conversational turns.\n"
            "2. BIM INTERNAL DATA STANDARDIZATION: Regardless of the conversational language used, all internal structural IDs, keys, "
            "   and final Revit element names (such as level names and grid labels) MUST be standard English (e.g. translate 'الأرضي' to 'Ground Floor', "
            "   or 'المستوى الأول' to 'First Floor'). This ensures standard parameter compliance in the model database.\n\n"

            "CONVERSATIONAL VALIDATION LOOP:\n"
            "If the cumulative details are incomplete or contradictory, set 'is_valid' to false and write a clear, friendly "
            "clarification message in 'clarification_message'. Only set 'is_valid' to true when the parameters are complete and unambiguous.\n\n"

            "Output MUST be raw JSON matching this schema:\n"
            "{\n"
            '  "is_valid": bool,\n'
            '  "clarification_message": "Conversational status update or clarification questions in the user\'s language",\n'
            '  "kpis": {\n'
            '     "total_length_m": float or null,\n'
            '     "total_width_m": float or null,\n'
            '     "total_height_m": float or null,\n'
            '     "footprint_area_sqm": float or null,\n'
            '     "total_floors": int,\n'
            '     "total_grids": int\n'
            '  },\n'
            '  "proposed_delta": {\n'
            '     "levels": {\n'
            '        "create": [ { "id": "lvl_b1", "name": "Basement 1", "elevation": -3.6, "create_floor_plan": true } ],\n'
            '        "update": [ { "id": "lvl_1", "name": "Level 1", "elevation": 4.2 } ],\n'
            '        "delete": [ "string_id_or_name" ]\n'
            '     },\n'
            '     "grids": {\n'
            '        "create": [ { "id": "g_x_1", "name": "1", "axis": "X", "position": 0.0 } ],\n'
            '        "update": [ { "id": "g_y_a", "name": "A", "axis": "Y", "position": 0.0 } ],\n'
            '        "delete": [ "string_id_or_name" ]\n'
            '     }\n'
            '  }\n'
            "}\n"
        )

    @staticmethod
    def fetch_available_models(api_key: str) -> list:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                output_models = []
                for m in res_json.get("models", []):
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        m_id = m["name"].replace("models/", "")
                        if "vision" not in m_id and "bidi" not in m_id:
                            output_models.append({"id": m_id, "name": m.get("displayName", m_id)})
                return sorted(output_models, key=lambda x: x["id"])
        except Exception as e:
            raise RuntimeError(f"Could not query Gemini models: {e}")

    def query_intent(self, chat_history: list, existing_context: dict) -> dict:
        combined_payload = {
            "conversation_history": chat_history,
            "existing_model_state": existing_context
        }
        
        request_data = {
            "contents": [{"parts": [{"text": json.dumps(combined_payload)}]}],
            "generationConfig": {"responseMimeType": "application/json"},
            "systemInstruction": {"parts": [{"text": self.system_instruction}]}
        }
        
        json_bytes = json.dumps(request_data).encode("utf-8")
        req = urllib.request.Request(
            self.api_url, 
            data=json_bytes, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                output_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(output_text)
        except urllib.error.HTTPError as he:
            err_content = he.read().decode("utf-8")
            raise RuntimeError(f"API HTTP Error {he.code}: {err_content}")
        except Exception as e:
            raise RuntimeError(f"API Connection error: {e}")