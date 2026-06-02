# -*- coding: utf-8 -*-
"""
Agent Loop — Gemini agentic conversation runtime.

Provides:
    - run_agent_loop(): Runs the Gemini chat session with smart context
      fetching and tool execution.
"""
import json
from google import genai
from google.genai import types
from config import ACTIVE_MODEL


# Initialize the Gemini API client
client = genai.Client()

# =====================================================================
# SYSTEM PROMPT — SMART CONTEXT FETCHING
# =====================================================================

SYSTEM_PROMPT = (
    "You are an active AI BIM design assistant operating inside Autodesk Revit. "
    "You have direct access to execute architectural layout modifications using your tools.\n\n"
    "WORKFLOW — follow these steps in order:\n"
    "1. ANALYZE the user's request to determine what information you need.\n"
    "2. FETCH only the relevant context using the fetch tools:\n"
    "   - Use fetch_levels when you need level IDs or elevations (e.g. before placing families or sizing grids).\n"
    "   - Use fetch_grids when you need existing grid names and extents (e.g. before creating new grids).\n"
    "   - Use fetch_families when you need to know what families and types are loaded (e.g. before placing a family instance).\n"
    "   - Use fetch_sheets when you need existing sheet numbers (e.g. before creating a new sheet).\n"
    "   - Use fetch_project_info for basic document identification.\n"
    "3. PLAN your actions based on the fetched data.\n"
    "4. EXECUTE using the action tools (create_grid, place_family, create_sheet, etc.).\n\n"
    "EFFICIENCY RULES:\n"
    "- Do NOT fetch data you do not need. For example, to create a grid you may need levels and existing grids, "
    "but you do NOT need families or sheets.\n"
    "- You may call multiple fetch tools in parallel if you need data from several categories.\n"
    "- Always check fetched data before acting (e.g. verify a level ID exists, avoid duplicate grid names)."
)


# =====================================================================
# AGENT RUNTIME LOOP
# =====================================================================

def run_agent_loop(user_prompt: str, gemini_tools: list, tool_map: dict):
    """
    Runs the Gemini agentic loop with auto-discovered tools.

    The agent is instructed to fetch only the context it needs before
    executing action tools — no upfront bulk context loading.

    Args:
        user_prompt:  The raw natural language request from the user.
        gemini_tools: List of FunctionDeclaration objects built from the bridge.
        tool_map:     Dict mapping tool names to their dispatcher callables.
    """
    print(f"\n[Agent Initialization] Processing user request...")

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=[types.Tool(function_declarations=gemini_tools)],
        temperature=0.0
    )

    chat = client.chats.create(model=ACTIVE_MODEL, config=config)
    response = chat.send_message(user_prompt)

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
