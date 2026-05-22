# tools/generate_payload.py
import os
import sys
import json
import google.generativeai as genai

# Setup search paths to locate the payload compiler
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from lib.Core.payload_compiler import PayloadCompiler

# Configure Gemini with user-provided parameters
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyCxZW8zex0P3TnvApNnLLwG5_pR4yMcusI")
MODEL_NAME = "gemini-2.5-flash"

genai.configure(api_key=API_KEY)

# Define the exact JSON schema requested by the compiler inside the system instructions
SYSTEM_INSTRUCTION = (
    "You are an expert structural BIM/VDC coordinator. Your task is to extract structural setup parameters "
    "from unstructured design briefs and convert them into a structured JSON payload representing project intents.\n\n"
    "You must return ONLY a JSON object matching this schema:\n"
    "{\n"
    '  "project_name": "String name",\n'
    '  "units": "mm" or "m" or "ft",\n'
    '  "coordinate_system": "project_base_point" or "survey_point" or "internal_origin",\n'
    '  "levels": [\n'
    '     { "name": "Level Name", "height_from_previous": float, "create_floor_plan": bool }\n'
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
    "1. 'height_from_previous' represents the distance from the immediately preceding level in the list.\n"
    "2. The levels list must be sorted from lowest elevation to highest elevation.\n"
    "3. The last element of x_axis and y_axis bays must have a 'spacing_to_next' value of 0.0.\n"
    "4. Do not include markdown formatting like ```json or trailing comments. Output raw JSON syntax only."
)

def prompt_gemini_for_intent(design_brief: str) -> dict:
    """Sends the design brief to the Gemini model and parses the structured response."""
    try:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            generation_config={"response_mime_type": "application/json"},
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        response = model.generate_content(design_brief)
        
        # Parse output text directly to python dictionary
        intent_dict = json.loads(response.text)
        return intent_dict
        
    except json.JSONDecodeError as jde:
        raise ValueError(f"Failed to decode valid JSON from Gemini response: {jde}. Raw response was: {response.text}")
    except Exception as e:
        raise RuntimeError(f"Gemini API execution error: {e}")

def get_multiline_input() -> str:
    """Prompts user to enter a multi-line design brief in the console."""
    print("\n📝 ENTER YOUR DESIGN BRIEF (Press Enter + Ctrl-D or Ctrl-Z on Windows to finish):")
    print("-" * 70)
    lines = sys.stdin.read()
    print("-" * 70)
    return lines.strip()

def main():
    print("==================================================")
    print("          AI BIM AGENT - PAYLOAD GENERATOR        ")
    print("==================================================")
    
    # Get dynamic design brief from the console
    user_brief = get_multiline_input()
    
    if not user_brief:
        print("⚠️ Empty design brief. Program terminated.")
        return

    print("\n🤖 Querying Gemini API (Model: {})...".format(MODEL_NAME))
    try:
        # Step 1: Query Gemini
        intent_data = prompt_gemini_for_intent(user_brief)
        
        # Save a reference copy of extracted intent
        intent_log_path = os.path.join(PROJECT_ROOT, "docs", "last_ai_intent.json")
        os.makedirs(os.path.dirname(intent_log_path), exist_ok=True)
        with open(intent_log_path, "w") as f:
            json.dump(intent_data, f, indent=4)
        print("✅ Extracted structural intent written to docs/last_ai_intent.json")

        # Step 2: Compile structure geometrically 
        print("🧮 Compiling coordinates and bounding extents...")
        compiler = PayloadCompiler(intent_data, grid_offset_buffer=5000.0) # 5m offset
        compiled_payload = compiler.compile()

        # Step 3: Write payload.json
        payload_path = os.path.join(PROJECT_ROOT, "payload.json")
        with open(payload_path, "w") as f:
            json.dump(compiled_payload, f, indent=4)
            
        print("\n🎉 SUCCESS! Payload compiled and written to: payload.json")
        print("You can now open Revit and click 'Build From AI' to execute.")

    except Exception as e:
        print(f"\n💥 ERROR: {e}")

if __name__ == "__main__":
    main()