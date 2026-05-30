# -*- coding: utf-8 -*-
import json
import sys
import requests
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, REVIT_BRIDGE_URL

client = genai.Client()

def get_revit_context() -> dict:
    """Queries the live Revit model context from the running bridge."""
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
    """
    Places a specific family type instance inside the active Revit document 
    at the defined absolute X, Y, Z coordinates and level constraint.
    
    Args:
        family_name: The name of the family to place (e.g., "Desk").
        type_name: The specific type name of the family (e.g., "60\" x 30\"").
        x: The X coordinate in decimal feet relative to internal origin.
        y: The Y coordinate in decimal feet relative to internal origin.
        z: The Z coordinate in decimal feet relative to internal origin.
        level_id: The unique ID string of the target constraint Level element.
    """
    print(f"\n[Tool Execution] Sending placement request to Revit Bridge...")
    print(f" -> Family: {family_name} | Type: {type_name}")
    print(f" -> Position: ({x}, {y}, {z}) | Level ID: {level_id}")

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

TOOL_MAP = {
    "place_family_instance": place_family_instance
}

def run_agent_loop(user_prompt: str, project_context: str):
    print(f"\n[Agent Initialization] Processing user request...")
    
    tools = [place_family_instance]
    
    config = types.GenerateContentConfig(
        system_instruction=(
            "You are an active AI BIM design assistant operating inside Autodesk Revit. "
            "You have direct access to execute architectural layout modifications utilizing your tools. "
            "Examine the project metadata context closely, then call your tools to fulfill the user request. "
            "Always match the user-requested family types and levels with the available elements in the project context."
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
    # 1. Pull dynamic metadata directly from Revit
    real_context = get_revit_context()
    
    print("\nSuccessfully loaded live model context!")
    print(f" -> Current Document: {real_context.get('document_title')}")
    print(f" -> Found {len(real_context.get('levels', []))} level(s)")
    print(f" -> Found {len(real_context.get('families', {}))} family definitions")

    # Prompt user for natural language input
    user_request = "Place a standard 60\" x 30\" Desk on Level 1 at coordinates X=10, Y=5, Z=0."
    
    run_agent_loop(user_prompt=user_request, project_context=json.dumps(real_context))