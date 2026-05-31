# -*- coding: utf-8 -*-
import json
import sys
import requests
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, REVIT_BRIDGE_URL

# Initialize the Gemini API client
client = genai.Client()

# Dynamic registries
ACTIVE_TOOLS = []  # Automatically populated with tool functions for Gemini
TOOL_MAP = {}      # Automatically maps string names to Python function objects

def register_tool(func):
    """
    Decorator that dynamically registers a function as an active 
    Gemini tool and maps it to our local tool execution engine.
    """
    ACTIVE_TOOLS.append(func)
    TOOL_MAP[func.__name__] = func
    return func

def call_revit_bridge(action: str, parameters: dict, timeout: int = 30) -> dict:
    """
    Sends unified JSON requests to the Revit Bridge. 
    If the network call fails, it provides descriptive diagnostic errors.
    """
    payload = {
        "action": action,
        "parameters": parameters
    }
    try:
        response = requests.post(REVIT_BRIDGE_URL, json=payload, timeout=timeout)
        return response.json()
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": (
                f"Bridge communication failure running action '{action}' "
                f"with parameters {json.dumps(parameters)}. "
                f"Network exception: {str(e)}"
            )
        }

# =====================================================================
# SYSTEM TOOLS (Automatically Registered with Inline Diagnostic Logging)
# =====================================================================

def get_revit_context() -> dict:
    """Queries the dynamic context metadata directly from Revit."""
    print("[Revit Connection] Querying active project metadata...")
    return call_revit_bridge("get_context", {}, timeout=15)

@register_tool
def place_family_instance(family_name: str, type_name: str, x: float, y: float, z: float, level_id: str) -> dict:
    """Places a family symbol instance at the specified coordinates."""
    print(f"\n[Tool Execution] Placing family instance '{family_name}'...")
    result = call_revit_bridge("place_family", {
        "family_name": family_name,
        "type_name": type_name,
        "coordinates": {"x": x, "y": y, "z": z},
        "level_id": level_id
    })
    print(f"[Observation from Revit] Response: {json.dumps(result, indent=2)}")
    return result

@register_tool
def create_sheet(sheet_number: str, sheet_name: str) -> dict:
    """
    Creates a new sheet layout (sheet plan view) in the active project.
    """
    print(f"\n[Tool Execution] Sending sheet creation request to Revit...")
    print(f" -> Sheet: {sheet_number} - {sheet_name}")
    result = call_revit_bridge("create_sheet", {
        "sheet_number": sheet_number,
        "sheet_name": sheet_name
    })
    print(f"[Observation from Revit] Response: {json.dumps(result, indent=2)}")
    return result

@register_tool
def create_grid(name: str, start_x: float, start_y: float, end_x: float, end_y: float) -> dict:
    """
    Creates a linear reference gridline in the Revit project.
    
    Args:
        name: The display name of the grid (e.g. 'Grid A', 'Grid 1').
        start_x: The starting X coordinate in feet.
        start_y: The starting Y coordinate in feet.
        end_x: The ending X coordinate in feet.
        end_y: The ending Y coordinate in feet.
    """
    print(f"\n[Tool Execution] Creating reference gridline '{name}'...")
    result = call_revit_bridge("create_grid", {
        "name": name,
        "start_point": {"x": start_x, "y": start_y},
        "end_point": {"x": end_x, "y": end_y}
    })
    print(f"[Observation from Revit] Response: {json.dumps(result, indent=2)}")
    return result

# =====================================================================
# AGENT RUNTIME LOOP
# =====================================================================

def run_agent_loop(user_prompt: str, project_context: str):
    print(f"\n[Agent Initialization] Processing user request...")
    
    config = types.GenerateContentConfig(
        system_instruction=(
            "You are an active AI BIM design assistant operating inside Autodesk Revit. "
            "You have direct access to execute architectural layout modifications utilizing your tools. "
            "Examine the project metadata context closely, then call your tools to fulfill the user request."
        ),
        tools=ACTIVE_TOOLS,
        temperature=0.0
    )
    
    chat = client.chats.create(model="gemini-2.5-flash", config=config)
    composed_prompt = f"Active Model Context:\n{project_context}\n\nUser Request: {user_prompt}"
    
    response = chat.send_message(composed_prompt)
    
    # Standard fallback loop in case automatic tool handling is disabled or overridden
    while response.function_calls:
        for call in response.function_calls:
            tool_name = call.name
            args = call.args
            
            if tool_name in TOOL_MAP:
                observation = TOOL_MAP[tool_name](**args)
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": observation}
                    )
                )
            else:
                response = chat.send_message(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": {"status": "error", "message": f"Tool '{tool_name}' unregistered."}}
                    )
                )
                
    print("\n[Agent Loop Complete] Final Response:")
    print(response.text)
    return response.text

if __name__ == "__main__":
    real_context = get_revit_context()
    
    if real_context.get("status") == "error":
        print(f"\n[Error] {real_context.get('message')}")
        sys.exit(1)
        
    print("\nSuccessfully loaded live model context!")
    print(f" -> Current Document: {real_context.get('document_title')}")
    print(f" -> Found {len(real_context.get('levels', []))} level(s)")

    user_request = "Draw a new reference gridline in the project named 'Grid Alpha'. Start it at coordinates 0,0 and run it to 150,0."
    
    run_agent_loop(user_prompt=user_request, project_context=json.dumps(real_context))