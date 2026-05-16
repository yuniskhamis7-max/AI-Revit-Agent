"""Payload file utilities.

The tools layer handles deterministic JSON loading and formatting only. It does
not know about pyRevit UI or Revit execution.
"""

import json
import os


def list_payload_files(payloads_dir):
    """Return JSON payload files from the payload folder."""
    if not os.path.isdir(payloads_dir):
        return []
    return [
        os.path.join(payloads_dir, name)
        for name in sorted(os.listdir(payloads_dir))
        if name.lower().endswith(".json")
    ]


def load_payload_file(path):
    """Load a JSON payload file and return a structured load result."""
    try:
        with open(path, "r") as payload_file:
            return {
                "success": True,
                "path": path,
                "payload": json.load(payload_file),
                "error": None,
            }
    except Exception as error:
        return {
            "success": False,
            "path": path,
            "payload": None,
            "error": str(error),
        }


def parse_payload_text(text):
    """Parse edited payload JSON text into structured payload data."""
    try:
        return {
            "success": True,
            "payload": json.loads(text),
            "error": None,
        }
    except Exception as error:
        return {
            "success": False,
            "payload": None,
            "error": str(error),
        }


def payload_to_text(payload):
    """Format payload data for preview and optional editing."""
    return json.dumps(payload, indent=4, sort_keys=True)
