"""Runtime executor for pyRevit command execution.

The executor is the single callable surface used by the pyRevit button.
"""

from app.main import bootstrap


def run():
    """Run the current automation workflow."""
    bootstrap()
