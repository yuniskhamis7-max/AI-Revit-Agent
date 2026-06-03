# -*- coding: utf-8 -*-
"""
Integration test script for running a live Gemini AI Revit Agent scenario.
"""
import sys
import os

daemon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if daemon_dir not in sys.path:
    sys.path.insert(0, daemon_dir)

from bridge.client import load_tools_from_bridge
from agent.loop import run_agent_loop


def run_test_scenario(scenario_prompt):
    print("=====================================================================")
    print("RUNNING AGENT SCENARIO TEST")
    print(f"Prompt: {scenario_prompt}")
    print("=====================================================================")

    # 1. Discover tools
    gemini_tools, tool_map = load_tools_from_bridge()

    # 2. Run agent loop
    run_agent_loop(
        user_prompt=scenario_prompt,
        gemini_tools=gemini_tools,
        tool_map=tool_map
    )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = (
            "Verify the levels in the project first. Then create a sheet named "
            "'A102 FLOOR PLAN' with number 'A102'. Next, create a grid named "
            "'Grid Z' starting at (0, 0) and ending at (50, 50) relative to "
            "the Project Base Point."
        )

    run_test_scenario(prompt)
