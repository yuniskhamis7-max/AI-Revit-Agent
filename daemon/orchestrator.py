# -*- coding: utf-8 -*-
import json
import sys
import requests
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, REVIT_BRIDGE_URL

client = genai.Client()

def get_revit_context() -> dict:
    """Queries the dynamic context metadata directly from Revit."""
    print("[Revit Connection] Querying active project metadata...")
    payload = {"action": "get_context"}
    try:
        response = requests.post(REVIT_BRIDGE_URL, json=payload, timeout=15)
        response_json = response.json()
        if response_json.get("status") == "success":
            return response_json
        else:
            print(f"Error: Bridge failed to retrieve context: {response_json.get('message')}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"Error: Could not connect to the Revit Bridge at {REVIT_BRIDGE_URL}.")
        print("Please verify that the 'Start Bridge' add-in is running inside Revit.")
        sys.exit(1)

def place_family_instance(family_name: str, type_name: str, x: float, y: float, z: float, level_id: str) -> dict:
    """Places a family symbol instance at the specified coordinates."""
    payload = {
        "action": "place_family",
        "parameters": {
            "family_name": family_name,
            "type_name": type_name,
            "coordinates": {"x": x, "y": y, "z": z},
            "level_id": level_id
        }
    }
    try:
        response = requests.post(REVIT_BRIDGE_URL, json=payload, timeout=30)
        return response.json()
    except requests.exceptions.RequestException as e:
         return {"status": "error", "message": f"Bridge communication failure: {str(e)}"}

def create_sheet(sheet_number: str, sheet_name: str) -> dict:
    """
    Creates a new sheet layout (sheet plan view) in the active project.
    
    Args:
        sheet_number: The unique identifier code for the sheet (e.g. 'A101', 'A102').
        sheet_name: The descriptive title of the sheet layout (e.g. 'FIRST FLOOR PLAN').
    """
    print(f"\n[Tool Execution] Sending sheet creation request to Revit...")
    print(f" -> Sheet: {sheet_number} - {sheet_name}")
    payload = {
        "action": "create_sheet",
        "parameters": {
            "sheet_number": sheet_number,
            "sheet_name": sheet_name
        }
    }
    try:
        response = requests.post(REVIT_BRIDGE_URL, json=payload, timeout=30)
        return response.json()
    except requests.exceptions.RequestException as e:
         return {"status": "error", "message": f"Bridge communication failure: {str(e)}"}

TOOL_MAP = {
    "place_family_instance": place_family_instance,
    "create_sheet": create_sheet
}

def run_agent_loop(user_prompt: str, project_context: str):
    print(f"\n[Agent Initialization] Processing user request...")
    
    # Expose the tools directly to the Gemini Agent model
    tools = [place_family_instance, create_sheet]
    
    config = types.GenerateContentConfig(
        system_instruction=(
            "You are an active AI BIM design assistant operating inside Autodesk Revit. "
            "You have direct access to execute architectural layout modifications utilizing your tools. "
            "Examine the project metadata context closely, then call your tools to fulfill the user request."
        ),
        tools=tools,
        temperature=0.0
    )
    
    chat = client.chats.create(model="gemini-2.5-flash", config=config)
    composed_prompt = f"Active Model Context:\n{project_context}\n\nUser Request: {user_prompt}"
    
    response = chat.send_message(composed_prompt)
    
    while response.function_calls:
        for call in response.function_calls:
            tool_name = call.name
            args = call.args
            
            print(f"\n[Agent Thought] Calling Tool: {tool_name}")
            
            if tool_name in TOOL_MAP:
                observation = TOOL_MAP[tool_name](**args)
                print(f"[Observation from Revit] Response: {json.dumps(observation, indent=2)}")
                
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": observation}
                    )
                )
            else:
                error_msg = f"Requested tool '{tool_name}' is not registered."
                print(f"[Agent Error] {error_msg}")
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": {"status": "error", "message": error_msg}}
                    )
                )
                
    print("\n[Agent Loop Complete] Final Response:")
    print(response.text)
    return response.text

if __name__ == "__main__":
    # Get live context from Revit
    real_context = get_revit_context()
    
    print("\nSuccessfully loaded live model context!")
    print(f" -> Current Document: {real_context.get('document_title')}")
    print(f" -> Found {len(real_context.get('levels', []))} level(s)")

    # Execute dynamic sheet layout query
    user_request = "Create a new sheet layout for the architectural division. Code it A102 and title it LOBBY ELEVATIONS."
    
    run_agent_loop(user_prompt=user_request, project_context=json.dumps(real_context))