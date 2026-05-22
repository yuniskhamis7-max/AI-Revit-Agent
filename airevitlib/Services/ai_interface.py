# lib/ai_interface.py
import os
import json
import urllib.request
import urllib.error

class GeminiClient:
    """Manages secure REST-based connectivity to Google Gemini API."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent?key={}".format(
            self.model_name, self.api_key
        )
        self.system_instruction = (
            "You are an expert structural BIM/VDC coordinator. Your task is to extract structural setup parameters "
            "from unstructured design briefs and convert them into a structured JSON payload representing project intents.\n\n"
            "You must return ONLY a JSON object matching this schema:\n"
            "{\n"
            '  "project_name": "String name",\n'
            '  "units": "mm" or "m" or "ft",\n'
            '  "coordinate_system": "project_base_point" or "survey_point" or "internal_origin",\n'
            '  "levels": [\n'
            '     { "name": "Level Name", "elevation": float, "create_floor_plan": bool }\n'
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