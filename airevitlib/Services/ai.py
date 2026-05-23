# airevitlib/services/ai.py
import json
import urllib.request
import urllib.error

class GeminiClient:
    """Manages stateful multi-turn conversational validation loops."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
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

            "CRITICAL CONVERSATIONAL MEMORY RULE:\n"
            "1. Read the entire 'conversation_history' from first to last to understand the context and the user's choices.\n"
            "2. Compare the final consolidated user design intent against the actual 'existing_model_state'.\n"
            "3. If the user confirms a deletion of an existing element, you MUST add that element's ID/Name to the deletion list.\n\n"

            "CRITICAL DESIGN RULES:\n"
            "1. LANGUAGE STANDARDIZATION: Keep all internal keys, structural IDs, and names in English "
            "   (e.g., translate 'الأرضي' to 'Ground Floor'). Keep conversational messages friendly and in the user's language.\n\n"

            "CONVERSATIONAL VALIDATION LOOP:\n"
            "If the cumulative details are incomplete or contradictory, set 'is_valid' to false and write a clear, friendly "
            "clarification message in 'clarification_message'. Only set 'is_valid' to true when the parameters are complete and unambiguous.\n\n"

            "Output MUST be raw JSON matching this schema:\n"
            "{\n"
            '  "is_valid": bool,\n'
            '  "clarification_message": "Friendly, conversational status update or clarification questions",\n'
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