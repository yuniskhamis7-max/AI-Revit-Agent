# -*- coding: utf-8 -*-
"""
Revit Agent Bridge Connection Diagnostic Utility.

Tests connectivity to both the /tools/ and /execute/ endpoints,
verifying that individual fetch tools and the system get_context
tool respond correctly.
"""
import sys
import os
import json
import requests

# Ensure the daemon directory is on the path for config imports
daemon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if daemon_dir not in sys.path:
    sys.path.insert(0, daemon_dir)

from config import REVIT_EXECUTE_URL, REVIT_DISCOVERY_URL


def test_bridge_connection():
    print("=====================================================================")
    print("REVIT AGENT BRIDGE CONNECTION DIAGNOSTIC UTILITY")
    print("=====================================================================")

    # 1. Check tools discovery endpoint
    print(f"\n1. Connecting to Tool Discovery Endpoint: {REVIT_DISCOVERY_URL} ...")
    try:
        response = requests.get(REVIT_DISCOVERY_URL, timeout=5)
        if response.status_code == 200:
            print("[SUCCESS] Tool discovery response received.")
            data = response.json()
            if data.get("status") == "success":
                tools = data.get("tools", [])
                print(f" -> Found {len(tools)} registered tool(s) in Revit:")

                fetch_tools  = []
                action_tools = []
                for t in tools:
                    if t["name"].startswith("fetch_"):
                        fetch_tools.append(t)
                    else:
                        action_tools.append(t)

                if fetch_tools:
                    print(f"\n   FETCH TOOLS ({len(fetch_tools)}):")
                    for t in fetch_tools:
                        print(f"    - '{t['name']}': {t['description'][:60]}...")

                if action_tools:
                    print(f"\n   ACTION TOOLS ({len(action_tools)}):")
                    for t in action_tools:
                        print(f"    - '{t['name']}': {t['description'][:60]}...")
            else:
                print(f"[WARNING] Bridge returned non-success status: {data.get('message')}")
        else:
            print(f"[FAILURE] Endpoint returned HTTP {response.status_code}.")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Could not connect to discovery endpoint. Is Revit running and the bridge started?")
        print(f"Details: {e}")
        return False

    # 2. Test individual fetch tools
    fetch_tools_to_test = [
        ("fetch_project_info", "Project Info"),
        ("fetch_levels",       "Levels"),
        ("fetch_grids",        "Grids"),
        ("fetch_families",     "Families"),
        ("fetch_sheets",       "Sheets"),
    ]

    print(f"\n2. Testing Individual Fetch Tools via Execute Endpoint...")
    for tool_name, label in fetch_tools_to_test:
        payload = {"tool": tool_name, "input": {}}
        try:
            response = requests.post(REVIT_EXECUTE_URL, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    summary_parts = []
                    for key, val in data.items():
                        if key in ("status", "coordinate_reference"):
                            continue
                        if isinstance(val, list):
                            summary_parts.append(f"{len(val)} {key}")
                        elif isinstance(val, dict):
                            summary_parts.append(f"{len(val)} {key}")
                        else:
                            summary_parts.append(f"{key}: {val}")
                    summary = ", ".join(summary_parts) if summary_parts else "OK"
                    print(f"   [OK]   {label:16s} -> {summary}")
                else:
                    print(f"   [FAIL] {label:16s} -> {data.get('message')}")
            else:
                print(f"   [FAIL] {label:16s} -> HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"   [FAIL] {label:16s} -> {e}")
            return False

    # 3. Test system tool get_context (diagnostic)
    print(f"\n3. Testing System Tool 'get_context' (diagnostic)...")
    payload = {"tool": "get_context", "input": {}}
    try:
        response = requests.post(REVIT_EXECUTE_URL, json=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                print(f"   [OK] Document: {data.get('document_title')}")
                print(f"   [OK] Levels:   {len(data.get('levels', []))}")
                print(f"   [OK] Families: {len(data.get('families', {}))}")
            else:
                print(f"   [FAIL] {data.get('message')}")
        else:
            print(f"   [FAIL] HTTP {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"   [FAIL] {e}")
        return False

    print("\n=====================================================================")
    print("[SUCCESS] Revit Agent Bridge communication verified fully.")
    print("=====================================================================")
    return True


if __name__ == "__main__":
    success = test_bridge_connection()
    sys.exit(0 if success else 1)
