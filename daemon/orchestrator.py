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

    # 2. Interactive prompt loop
    print("\n=====================================================================")
    print("  REVIT AI AGENT — Ready")
    print("  Type your request below. Type 'quit' or 'exit' to stop.")
    print("=====================================================================")

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

        run_agent_loop(
            user_prompt=user_request,
            gemini_tools=gemini_tools,
            tool_map=tool_map
        )