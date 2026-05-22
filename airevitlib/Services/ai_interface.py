# airevitlib/services/ai_interface.py
import os
import json
import urllib.request
import urllib.error

class GeminiClient:
    """Manages secure REST-based connectivity to Google Gemini API with Multilingual support."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}".format(
            self.model_name, self.api_key
        )
        self.system_instruction = (
            "You are an expert structural BIM/VDC coordinator. Your task is to extract structural setup parameters "
            "from unstructured design briefs and convert them into a structured JSON payload representing project intents.\n\n"
            
            "MULTILINGUAL PROCESSING RULES:\n"
            "1. The user brief may be submitted in various languages (e.g. Spanish, French, German, Arabic, Chinese, etc.).\n"
            "2. You must read and understand the brief in its native language.\n"
            "3. No matter what language the brief is submitted in, you must output all keys, names, and labels "
            "translated into ENGLISH inside the final JSON payload (e.g., 'Sótano' -> 'Basement', 'Erdgeschoss' -> 'Ground Floor').\n"
            "4. All keys in the JSON schema must remain strictly in English.\n\n"

            "CRITICAL UNIT NORMALIZATION RULE:\n"
            "You must perform any necessary unit conversions to ensure that all numerical values in the final JSON "
            "are scaled and represented in the target unit specified in the 'units' key.\n"
            "For example, if the brief text describes level heights or grid spacings in meters (e.g., '3.5 meters', '6m') "
            "but the target 'units' is specified as 'mm', you MUST mathematically scale those values by multiplying them "
            "by 1000 before writing them to the JSON (e.g., '3.5 meters' must be output as 3500.0, and '6m' must be 6000.0).\n"
            "Conversely, if the text describes millimeters but the target 'units' is 'm', divide the values by 1000.\n"
            "All coordinates, elevations, and spacings must be scaled to the selected unit scale.\n\n"

            "You must return ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "project_name": "String name (Must be translated to English)",\n'
            '  "units": "mm" or "m" or "ft",\n'
            '  "coordinate_system": "project_base_point" or "survey_point" or "internal_origin",\n'
            '  "levels": [\n'
            '     { "name": "Level Name (In English)", "elevation": float, "create_floor_plan": bool }\n'
            "  ],\n"
            '  "grids": {\n'
            '     "x_axis": {\n'
            '       "bays": [\n'
            '         { "label": "Grid Label", "spacing_to_next": float }\n'
            "       ]\n"
            "     },\n"
            '     "y_axis": {\n'
            '       "bays": [\n'
            '         { "label": "Grid Label", "spacing_to_next": float }\n'
            "       ]\n"
            "     }\n"
            "  }\n"
            "}\n\n"
            
            "CRITICAL RULES:\n"
            "1. 'elevation' represents the absolute height coordinate relative to the Ground Floor datum (which is 0.0).\n"
            "2. Levels must be sorted from lowest elevation (e.g. negative basement values) to highest elevation (roof).\n"
            "3. The last element of x_axis and y_axis bays must have a 'spacing_to_next' value of 0.0.\n"
            "4. Do not include markdown formatting like ```json. Output raw JSON syntax only."
        )

    @staticmethod
    def fetch_available_models(api_key: str) -> list:
        """Retrieves eligible context-limit metadata of Gemini models via GET REST request."""
        url = "https://generativelanguage.googleapis.com/v1beta/models?key={}".format(api_key)
        req = urllib.request.Request(url, method="GET")
        
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                
                output_models = []
                for m in res_json.get("models", []):
                    # Filter for generative models supporting content generation
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        m_id = m["name"].replace("models/", "")
                        # Exclude obsolete experimental versions
                        if "vision" not in m_id and "bidi" not in m_id:
                            output_models.append({
                                "id": m_id,
                                "name": m.get("displayName", m_id)
                            })
                return sorted(output_models, key=lambda x: x["id"])
                
        except Exception as e:
            raise RuntimeError("Could not query available Gemini models: {}".format(e))

    def query_intent(self, brief_text: str) -> dict:
        """Sends user design brief text to Gemini and retrieves structured program intent JSON."""
        request_data = {
            "contents": [{
                "parts": [{"text": brief_text}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json"
            },
            "systemInstruction": {
                "parts": [{"text": self.system_instruction}]
            }
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
            raise RuntimeError("API HTTP Error {}: {}".format(he.code, err_content))
        except Exception as e:
            raise RuntimeError("Gemini API Network failure: {}".format(e))