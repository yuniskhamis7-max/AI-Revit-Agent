# -*- coding: utf-8 -*-
"""
Agent Loop — Gemini agentic conversation runtime.

Provides:
    - run_agent_loop(): Runs the Gemini chat session with smart context
      fetching and tool execution.
"""
import json
import re
import time
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
from config import ACTIVE_MODEL


# Initialize the Gemini API client
client = genai.Client()

# Maximum number of retries when hitting 429 rate-limit errors
MAX_RETRIES = 5

# =====================================================================
# SYSTEM PROMPT — SMART CONTEXT FETCHING
# =====================================================================

SYSTEM_PROMPT = (
    "You are an active AI BIM design assistant operating inside Autodesk Revit. "
    "You have direct access to execute architectural layout modifications using your tools.\n\n"
    "WORKFLOW — follow these steps in order:\n"
    "1. ANALYZE the user's request to determine what information you need.\n"
    "2. FETCH context using the fetch tools:\n"
    "   - fetch_levels: level IDs, elevations, AND curve extents (curve_start_x, curve_end_x define building span).\n"
    "   - fetch_grids: existing grid names, positions, and spacing patterns.\n"
    "   - fetch_families: loaded family symbols for placing instances.\n"
    "   - fetch_sheets: existing sheet numbers.\n"
    "   - fetch_project_info: document identification.\n"
    "3. REASON about placement like a human modeler:\n"
    "   - BUILDING FOOTPRINT: If level curve_start_x/curve_end_x are present, use them for grid span. "
    "If NOT present, use existing grid positions OR the user-specified building dimensions.\n"
    "   - When placing grids: use the building footprint to determine grid LENGTH so they span appropriately. "
    "If existing grids are present, continue their spacing pattern.\n"
    "   - CROSSING GRIDS: When creating both vertical and horizontal grids, they MUST cross each other to form a grid network. "
    "Vertical grids have constant X and span Y. Horizontal grids have constant Y and span X. "
    "Both must use the SAME coordinate range so they intersect.\n"
    "   - When placing any element: align it with existing geometry. Use existing datum extents as reference.\n"
    "4. EXECUTE using the action tools.\n\n"
    "LEVEL DELETION ORDER (CRITICAL):\n"
    "- Revit requires at least one level to exist at all times.\n"
    "- When replacing levels: CREATE new levels FIRST, THEN delete old ones.\n"
    "- Never delete all levels before creating replacements.\n"
    "- After creating new levels, call fetch_levels again to get their curve_start_x and curve_end_x for grid placement.\n\n"
    "ZERO ASSUMPTIONS RULE (CRITICAL):\n"
    "- NEVER guess, assume, or invent any parameter values (names, elevations, dimensions, coordinates, types, etc.).\n"
    "- If the user's request is missing ANY required information, you MUST ask them to provide it before proceeding.\n"
    "- Exception: If the user explicitly says 'assume' or 'use standard values', you may proceed with reasonable assumptions.\n"
    "- Examples: If user says 'create a level' without specifying name and elevation — ASK. "
    "If user says 'add grids' without specifying spacing and location — ASK. "
    "If user says 'place a door' without specifying type, location, and level — ASK.\n"
    "- A human modeler would clarify before modeling. You must do the same.\n"
    "- It is better to ask one extra question than to create something incorrectly.\n\n"
    "EFFICIENCY RULES:\n"
    "- Do NOT fetch data you do not need.\n"
    "- You may call multiple fetch tools in the same turn if you need data from several categories.\n"
    "- Always verify fetched data before acting (e.g. check IDs exist, avoid duplicates).\n"
    "- All coordinates are in Revit's internal coordinate system (feet). "
    "Convert user-specified metric values: 1 meter = 3.28084 feet."
)


def _extract_retry_delay(error) -> float:
    """
    Parse the retryDelay from a Gemini 429 error response.
    The error details may contain a retryDelay string like '4s' or '4.646620155s'.
    Falls back to 5 seconds if parsing fails.
    """
    try:
        error_str = str(error)
        match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?([\d.]+)s", error_str)
        if match:
            return float(match.group(1))
    except Exception:
        pass
    return 5.0


def _send_with_retry(chat, message, context_label: str):
    """
    Sends a message to the Gemini chat session with automatic retry
    on 429 RESOURCE_EXHAUSTED errors (free-tier rate limiting).

    Uses the retryDelay from the API response when available,
    otherwise falls back to exponential backoff.

    Args:
        chat:           The Gemini chat session.
        message:        The message payload (string or list of Parts).
        context_label:  Human-readable label for log messages.

    Returns:
        The model response object.

    Raises:
        The original error if retries are exhausted.
    """
    for attempt in range(MAX_RETRIES):
        try:
            return chat.send_message(message)
        except genai_errors.ClientError as e:
            # Only retry on 429 rate-limit errors
            if "429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e):
                raise

            wait_seconds = _extract_retry_delay(e)
            # Add a small buffer to ensure the quota window has fully reset
            wait_seconds = min(wait_seconds + 1.0, 60.0)

            print(f"\n[Rate Limit] {context_label} hit 429 quota limit. "
                  f"Waiting {wait_seconds:.1f}s before retry "
                  f"(attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait_seconds)

    # All retries exhausted — raise the last error
    raise RuntimeError(
        f"Gemini API rate limit persisted after {MAX_RETRIES} retries. "
        f"Consider upgrading your plan or reducing request frequency."
    )


# =====================================================================
# AGENT RUNTIME LOOP
# =====================================================================

def run_agent_loop(user_prompt: str, gemini_tools: list, tool_map: dict, chat=None) -> dict:
    """
    Runs the Gemini agentic loop with auto-discovered tools.

    The agent is instructed to fetch only the context it needs before
    executing action tools — no upfront bulk context loading.

    Args:
        user_prompt:  The raw natural language request from the user.
        gemini_tools: List of FunctionDeclaration objects built from the bridge.
        tool_map:     Dict mapping tool names to their dispatcher callables.
        chat:         Optional existing Gemini chat session for conversation continuity.
                      If None, a new session is created.

    Returns:
        A dict with:
            "response"     (str):  The final text from the model.
            "tool_timings" (list): Per-call timing records.
            "total_ms"     (float): Total execution time.
            "chat"         (object): The chat session (for reuse in next call).
    """
    print(f"\n[Agent Initialization] Processing user request...")
    session_start = time.perf_counter()
    all_tool_timings = []

    # Create or reuse the chat session
    if chat is None:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(function_declarations=gemini_tools)],
            temperature=0.0
        )
        chat = client.chats.create(model=ACTIVE_MODEL, config=config)

    response = _send_with_retry(chat, user_prompt, "Initial prompt")

    turn = 0
    while response.function_calls:
        turn += 1
        function_responses = []
        turn_timings = []

        for call in response.function_calls:
            tool_name = call.name
            args = dict(call.args)

            print(f"\n[Agent Thought] Calling Tool: '{tool_name}'")

            t0 = time.perf_counter()
            if tool_name in tool_map:
                observation = tool_map[tool_name](**args)
            else:
                error_msg = f"Requested tool '{tool_name}' is not registered in the current bridge session."
                print(f"[Agent Error] {error_msg}")
                observation = {"status": "error", "message": error_msg}
            duration_ms = (time.perf_counter() - t0) * 1000

            timing_record = {"tool": tool_name, "duration_ms": round(duration_ms, 1)}
            turn_timings.append(timing_record)
            all_tool_timings.append(timing_record)

            function_responses.append(
                types.Part.from_function_response(
                    name=tool_name,
                    response={"result": observation}
                )
            )

        # Print a concise per-turn timing summary
        timing_summary = ", ".join(
            f"{t['tool']} ({t['duration_ms']} ms)" for t in turn_timings
        )
        print(f"[Turn {turn} Timing] {timing_summary}")

        # Send all function responses collected in this turn back to the model at once
        response = _send_with_retry(chat, function_responses, f"Turn {turn} tool results")

    total_ms = round((time.perf_counter() - session_start) * 1000, 1)
    final_text = response.text or ""

    print(f"\n[Agent Loop Complete] Total time: {total_ms} ms | Tool calls: {len(all_tool_timings)}")
    print("[Final Response]")
    print(final_text)

    return {
        "response": final_text,
        "tool_timings": all_tool_timings,
        "total_ms": total_ms,
        "chat": chat
    }
