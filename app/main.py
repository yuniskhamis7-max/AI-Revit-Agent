"""Application bootstrap for AI Revit Agent.

The app layer owns startup concerns only: configuration, logging, and the
first handoff into Revit-facing UI code.
"""

from app.logger import configure_logging
from revit.ui import show_loaded_message


def bootstrap():
    """Initialize the application runtime for the current pyRevit command."""
    logger = configure_logging()
    logger.info("AI Revit Agent bootstrap started.")

    show_loaded_message()

    logger.info("AI Revit Agent bootstrap completed.")
