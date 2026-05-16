"""Logging setup for AI Revit Agent.

All runtime logs for this phase are written to logs/runtime. The setup is kept
small and deterministic so pyRevit button execution remains easy to diagnose.
"""

import logging
import os

from app.config import RUNTIME_LOG_DIR, RUNTIME_LOG_FILE


def configure_logging():
    """Create the runtime logger and ensure its file handler is ready."""
    if not os.path.exists(RUNTIME_LOG_DIR):
        os.makedirs(RUNTIME_LOG_DIR)

    logger = logging.getLogger("ai_revit_agent")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.FileHandler(RUNTIME_LOG_FILE)
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)

    return logger
