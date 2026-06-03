# -*- coding: utf-8 -*-
"""
Revit AI Agent — Orchestrator Daemon Entry Point.

Slim entry point that:
    1. Auto-discovers all tools from the Revit bridge via GET /tools/
    2. Runs an interactive agent loop where the AI fetches its own context
"""
import sys
from bridge.client import load_tools_from_bridge
from agent.loop import run_agent_loop


# =====================================================================
# ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    # 1. Auto-discover all tools from the Revit bridge (single source of truth)
    gemini_tools, tool_map = load_tools_from_bridge()

    # 2. Interactive prompt loop with persistent chat session
    print("\n=====================================================================")
    print("  REVIT AI AGENT — Ready")
    print("  Type your request below. Type 'quit' or 'exit' to stop.")
    print("  Type 'reset' to start a new conversation.")
    print("=====================================================================")

    chat = None  # Persistent chat session for conversation continuity

    while True:
        try:
            user_request = input("\n[You] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Agent] Session terminated by user.")
            break

        if not user_request:
            continue
        if user_request.lower() in ("quit", "exit"):
            print("[Agent] Goodbye.")
            break
        if user_request.lower() == "reset":
            chat = None
            print("[Agent] Conversation reset. Starting fresh session.")
            continue

        result = run_agent_loop(
            user_prompt=user_request,
            gemini_tools=gemini_tools,
            tool_map=tool_map,
            chat=chat  # Pass existing chat for continuity
        )

        # Preserve the chat session for the next request
        if isinstance(result, dict):
            chat = result.get("chat")
            timings = result.get("tool_timings", [])
            total_ms = result.get("total_ms", 0)
            if timings:
                print(f"\n[Performance] {len(timings)} tool call(s) in {total_ms} ms total")
        else:
            # Fallback for any legacy callers
            print(result)