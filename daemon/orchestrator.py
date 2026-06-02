# -*- coding: utf-8 -*-
import json
import os
import sys
import requests
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, REVIT_BRIDGE_URL, REVIT_TOOLS_URL, ACTIVE_MODEL

# Initialize the Gemini API client
client = genai.Client()

# =====================================================================
# REVIT BRIDGE COMMUNICATION
# =====================================================================

def call_revit_bridge(action: str, parameters: dict, timeout: int = 30) -> dict:
    """
    Sends a unified JSON request to the Revit Bridge /execute/ endpoint.
    Returns the parsed JSON response, or a descriptive error dict on failure.
    """
    payload = {"action": action, "parameters": parameters}
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

def get_revit_context() -> dict:
    """Queries the dynamic context metadata directly from Revit."""
    print("[Revit Connection] Querying active project metadata...")
    return call_revit_bridge("get_context", {}, timeout=15)

# =====================================================================
# DYNAMIC TOOL DISCOVERY
# =====================================================================

def load_tools_from_bridge() -> tuple:
    """
    Calls GET /tools/ on the Revit bridge and converts the returned JSON
    schemas into Gemini FunctionDeclaration objects plus a dispatch map.

    Returns:
        gemini_tools (list[types.FunctionDeclaration]): Ready for Gemini config.
        tool_map (dict[str, callable]): Maps tool name -> bridge dispatcher.

    Side effect:
        Writes schemas/tools.json relative to this script for inspection.
    """
    print("[Tool Discovery] Fetching tool registry from Revit bridge...")
    try:
        response = requests.get(REVIT_TOOLS_URL, timeout=15)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Tool Discovery] ERROR: Could not reach {REVIT_TOOLS_URL}. {e}")
        sys.exit(1)

    if data.get("status") != "success":
        print(f"[Tool Discovery] ERROR: Bridge returned error: {data.get('message')}")
        sys.exit(1)

    schemas = data.get("tools", [])
    print(f"[Tool Discovery] Found {len(schemas)} tool(s): {[s['name'] for s in schemas]}")

    # -- Persist schemas to disk for inspection and version tracking --
    schemas_dir = os.path.join(os.path.dirname(__file__), "..", "schemas")
    schemas_dir = os.path.normpath(schemas_dir)
    os.makedirs(schemas_dir, exist_ok=True)
    schemas_path = os.path.join(schemas_dir, "tools.json")
    with open(schemas_path, "w", encoding="utf-8") as f:
        json.dump(schemas, f, indent=2)
    print(f"[Tool Discovery] Schema snapshot saved -> {schemas_path}")

    # -- Build Gemini FunctionDeclarations and dispatcher map --
    gemini_tools = []
    tool_map = {}

    for schema in schemas:
        name = schema["name"]
        description = schema["description"]
        parameters = schema["parameters"]

        # Convert JSON schema dict to Gemini Schema object
        gemini_tools.append(
            types.FunctionDeclaration(
                name=name,
                description=description,
                parameters=types.Schema(
                    type=parameters.get("type", "object"),
                    properties={
                        k: types.Schema(
                            type=v.get("type", "string"),
                            description=v.get("description", "")
                        )
                        for k, v in parameters.get("properties", {}).items()
                    },
                    required=parameters.get("required", [])
                )
            )
        )

        # Build a generic bridge-dispatch closure for each tool
        def make_dispatcher(action_name: str):
            def dispatcher(**kwargs) -> dict:
                print(f"\n[Tool Execution] Calling '{action_name}' with args: {json.dumps(kwargs, indent=2)}")
                result = call_revit_bridge(action_name, kwargs)
                print(f"[Observation from Revit] Response: {json.dumps(result, indent=2)}")
                return result
            dispatcher.__name__ = action_name
            return dispatcher

        tool_map[name] = make_dispatcher(name)

    return gemini_tools, tool_map

# =====================================================================
# AGENT RUNTIME LOOP
# =====================================================================

def run_agent_loop(user_prompt: str, project_context: str, gemini_tools: list, tool_map: dict):
    """
    Runs the Gemini agentic loop with auto-discovered tools.

    Args:
        user_prompt:     The raw natural language request from the user.
        project_context: JSON string of the active Revit project metadata.
        gemini_tools:    List of FunctionDeclaration objects built from the bridge.
        tool_map:        Dict mapping tool names to their dispatcher callables.
    """
    print(f"\n[Agent Initialization] Processing user request...")

    config = types.GenerateContentConfig(
        system_instruction=(
            "You are an active AI BIM design assistant operating inside Autodesk Revit. "
            "You have direct access to execute architectural layout modifications utilizing your tools. "
            "Examine the project metadata context closely, then call your tools to fulfill the user request."
        ),
        tools=[types.Tool(function_declarations=gemini_tools)],
        temperature=0.0
    )

    chat = client.chats.create(model=ACTIVE_MODEL, config=config)
    composed_prompt = f"Active Model Context:\n{project_context}\n\nUser Request: {user_prompt}"

    response = chat.send_message(composed_prompt)

    while response.function_calls:
        function_responses = []
        for call in response.function_calls:
            tool_name = call.name
            args = dict(call.args)

            print(f"\n[Agent Thought] Calling Tool: '{tool_name}'")

            if tool_name in tool_map:
                observation = tool_map[tool_name](**args)
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": observation}
                    )
                )
            else:
                error_msg = f"Requested tool '{tool_name}' is not registered in the current bridge session."
                print(f"[Agent Error] {error_msg}")
                function_responses.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": {"status": "error", "message": error_msg}}
                    )
                )
        
        # Send all function responses collected in this turn back to the model at once
        response = chat.send_message(function_responses)

    print("\n[Agent Loop Complete] Final Response:")
    print(response.text)
    return response.text

# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    # 1. Fetch dynamic project context from Revit
    real_context = get_revit_context()

    if real_context.get("status") == "error":
        print(f"\n[Error] {real_context.get('message')}")
        sys.exit(1)

    print("\nSuccessfully loaded live model context!")
    print(f" -> Current Document: {real_context.get('document_title')}")
    print(f" -> Found {len(real_context.get('levels', []))} level(s)")

    # 2. Auto-discover all tools from the Revit bridge (single source of truth)
    gemini_tools, tool_map = load_tools_from_bridge()

    # 3. Run the agent with the discovered tools
    user_request = "Draw a new reference gridline in the project named 'Grid Alpha'. Start it at coordinates 0,0 and run it to 150,0."

    run_agent_loop(
        user_prompt=user_request,
        project_context=json.dumps(real_context),
        gemini_tools=gemini_tools,
        tool_map=tool_map
    )