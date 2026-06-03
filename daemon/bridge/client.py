# -*- coding: utf-8 -*-
"""
Bridge Client — Communication layer for the Revit Agent Bridge.

Provides:
    - call_revit_bridge():      Generic POST to /execute/ endpoint.
    - load_tools_from_bridge(): GET /tools/, builds Gemini declarations + dispatch map.
"""
import json
import os
import sys
import requests
from google.genai import types
from config import REVIT_EXECUTE_URL, REVIT_DISCOVERY_URL


# =====================================================================
# LOW-LEVEL BRIDGE COMMUNICATION
# =====================================================================

def call_revit_bridge(tool_name: str, tool_input: dict, timeout: int = 120) -> dict:
    """
    Sends a JSON request to the Revit Bridge /execute/ endpoint.

    Payload format:
        {"tool": "<name>", "input": {<args>}}

    Returns the parsed JSON response, or a descriptive error dict on failure.
    """
    payload = {"tool": tool_name, "input": tool_input}
    try:
        response = requests.post(REVIT_EXECUTE_URL, json=payload, timeout=timeout)
        return response.json()
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "message": (
                f"Bridge communication failure running tool '{tool_name}' "
                f"with input {json.dumps(tool_input)}. "
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

    Each tool's agent_instructions (if present) is merged into its description
    so Gemini reads the operational guidance at the exact moment it selects
    the tool — no system prompt changes required.

    Returns:
        gemini_tools (list[types.FunctionDeclaration]): Ready for Gemini config.
        tool_map (dict[str, callable]): Maps tool name -> bridge dispatcher.

    Side effect:
        Writes schemas/tools.json relative to the daemon directory for inspection.
    """
    print("[Tool Discovery] Fetching tool registry from Revit bridge...")
    try:
        response = requests.get(REVIT_DISCOVERY_URL, timeout=15)
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Tool Discovery] ERROR: Could not reach {REVIT_DISCOVERY_URL}. {e}")
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
        name        = schema["name"]
        description = schema["description"]
        parameters  = schema["parameters"]

        # Merge agent_instructions into the description that Gemini receives.
        # This places the "before calling" guidance directly on the tool declaration
        # so the model reads it at the exact moment it decides to call the tool.
        agent_instructions = schema.get("agent_instructions", "")
        if agent_instructions:
            full_description = description + "\n\nBEFORE CALLING: " + agent_instructions
        else:
            full_description = description

        # Convert JSON schema dict to Gemini Schema object
        def _build_property_schema(prop_def: dict) -> types.Schema:
            """
            Recursively converts a JSON Schema property definition to a
            Gemini types.Schema, correctly handling string, number, boolean,
            integer, and array types (with items for arrays).
            """
            prop_type = prop_def.get("type", "string").upper()
            prop_desc = prop_def.get("description", "")

            if prop_type == "ARRAY":
                items_def = prop_def.get("items", {})
                items_schema = _build_property_schema(items_def) if items_def else types.Schema(type="string")
                return types.Schema(type="array", description=prop_desc, items=items_schema)

            return types.Schema(type=prop_type, description=prop_desc)

        gemini_tools.append(
            types.FunctionDeclaration(
                name=name,
                description=full_description,
                parameters=types.Schema(
                    type=parameters.get("type", "object").upper(),
                    properties={
                        k: _build_property_schema(v)
                        for k, v in parameters.get("properties", {}).items()
                    },
                    required=parameters.get("required", [])
                )
            )
        )


        # Build a generic bridge-dispatch closure for each tool
        def make_dispatcher(t_name: str):
            def dispatcher(**kwargs) -> dict:
                print(f"\n[Tool Execution] Calling '{t_name}' with args: {json.dumps(kwargs, indent=2)}")
                result = call_revit_bridge(t_name, kwargs)
                print(f"[Observation from Revit] Response: {json.dumps(result, indent=2)}")
                return result
            dispatcher.__name__ = t_name
            return dispatcher

        tool_map[name] = make_dispatcher(name)

    return gemini_tools, tool_map
