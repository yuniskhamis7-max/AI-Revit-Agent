# -*- coding: utf-8 -*-
"""
Non-interactive test runner for the Revit AI agent.
Sends a single command, prints full output, then exits.
"""
import sys
import json
from bridge.client import load_tools_from_bridge
from agent.loop import run_agent_loop


def run_test(user_request):
    print(f"\n{'='*60}")
    print(f"  TEST: {user_request}")
    print(f"{'='*60}")

    gemini_tools, tool_map = load_tools_from_bridge()

    result = run_agent_loop(
        user_prompt=user_request,
        gemini_tools=gemini_tools,
        tool_map=tool_map
    )

    if isinstance(result, dict):
        print(f"\n[Response] {result.get('response', '(empty)')}")
        timings = result.get("tool_timings", [])
        total_ms = result.get("total_ms", 0)
        if timings:
            print(f"[Performance] {len(timings)} tool call(s) in {total_ms} ms total")
            for t in timings:
                print(f"  - {t['tool']}: {t['duration_ms']} ms")
    else:
        print(result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: test_runner.py \"<your command>\"")
        sys.exit(1)
    run_test(" ".join(sys.argv[1:]))
