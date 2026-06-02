# -*- coding: utf-8 -*-
import sys
import json
import requests

from config import REVIT_BRIDGE_URL, REVIT_TOOLS_URL

def test_bridge_connection():
    print("=====================================================================")
    print("REVIT AGENT BRIDGE CONNECTION DIAGNOSTIC UTILITY")
    print("=====================================================================")
    
    # 1. Check tools endpoint
    print(f"\n1. Connecting to Tools Registry Endpoint: {REVIT_TOOLS_URL} ...")
    try:
        response = requests.get(REVIT_TOOLS_URL, timeout=5)
        if response.status_code == 200:
            print("[SUCCESS] Tools registry response received.")
            data = response.json()
            if data.get("status") == "success":
                tools = data.get("tools", [])
                print(f" -> Found {len(tools)} registered tool(s) in Revit:")
                for t in tools:
                    print(f"    - '{t['name']}': {t['description']}")
            else:
                print(f"[WARNING] Bridge returned non-success status: {data.get('message')}")
        else:
            print(f"[FAILURE] Endpoint returned HTTP {response.status_code}.")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Could not connect to tools endpoint. Is Revit running and the bridge started?")
        print(f"Details: {e}")
        return False

    # 2. Check execute endpoint with get_context
    print(f"\n2. Connecting to Execute Endpoint with 'get_context': {REVIT_BRIDGE_URL} ...")
    payload = {"action": "get_context", "parameters": {}}
    try:
        response = requests.post(REVIT_BRIDGE_URL, json=payload, timeout=5)
        if response.status_code == 200:
            print("[SUCCESS] Execute endpoint response received.")
            data = response.json()
            if data.get("status") == "success":
                print(f" -> Active Document: {data.get('document_title')}")
                levels = data.get("levels", [])
                print(f" -> Found {len(levels)} Level(s):")
                for lvl in levels[:5]:
                    print(f"    - {lvl['name']} (Elevation: {lvl['elevation']} ft)")
                if len(levels) > 5:
                    print(f"    - ... and {len(levels) - 5} more")
                
                families = data.get("families", {})
                print(f" -> Loaded {len(families)} Family/Families:")
                for fam_name in list(families.keys())[:5]:
                    print(f"    - {fam_name}: {', '.join(families[fam_name][:3])}")
                if len(families) > 5:
                    print(f"    - ... and {len(families) - 5} more")
            else:
                print(f"[FAILURE] Bridge execution failed: {data.get('message')}")
        else:
            print(f"[FAILURE] Endpoint returned HTTP {response.status_code}.")
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Could not connect to execute endpoint.")
        print(f"Details: {e}")
        return False

    print("\n=====================================================================")
    print("[SUCCESS] Revit Agent Bridge communication verified fully.")
    print("=====================================================================")
    return True

if __name__ == "__main__":
    success = test_bridge_connection()
    sys.exit(0 if success else 1)
