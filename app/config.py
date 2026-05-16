"""Minimal configuration values for AI Revit Agent.

Configuration stays simple so runtime behavior has a clear place to grow
without spreading path constants across the codebase.
"""

import os


PROJECT_NAME = "ai_revit_agent"
APP_DISPLAY_NAME = "AI Revit Agent"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
PAYLOADS_DIR = os.path.join(DATA_DIR, "payloads")
CONTEXT_DIR = os.path.join(DATA_DIR, "context")
CONTEXT_SNAPSHOT_FILE = os.path.join(CONTEXT_DIR, "latest_snapshot.json")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
RUNTIME_LOG_DIR = os.path.join(LOGS_DIR, "runtime")
RUNTIME_LOG_FILE = os.path.join(RUNTIME_LOG_DIR, "ai_revit_agent.log")
