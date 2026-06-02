# -*- coding: utf-8 -*-
"""
Bridge Client — Communication layer for the Revit Agent Bridge.

Provides:
    - call_revit_bridge():     Generic POST to /execute/ endpoint.
    - load_tools_from_bridge(): GET /tools/, builds Gemini declarations + dispatch map.
"""
import json
import os
import sys
import requests
from google.genai import types
from config import REVIT_BRIDGE_URL, REVIT_TOOLS_URL


# =====================================================================
# LOW-LEVEL BRIDGE COMMUNICATION
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
        Writes schemas/tools.json relative to the daemon directory for inspection.
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
    schemas_dir = os.path.join(os.path.dirname(__file__), "..", "..", "schemas")
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
