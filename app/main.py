"""Application bootstrap for AI Revit Agent.

The app layer owns startup concerns only: configuration and logging setup.
Runtime orchestration and direct Revit API work live in their own layers.
"""

from app.logger import configure_logging


def bootstrap():
    """Initialize the application runtime for the current pyRevit command."""
    logger = configure_logging()
    logger.info("AI Revit Agent bootstrap started.")
    return logger
