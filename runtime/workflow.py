"""Workflow coordination placeholder.

Future workflow steps will live here. This module must remain free of direct
Revit API calls; it should coordinate runtime behavior only.
"""


def get_current_workflow_name():
    """Return the minimal phase-one workflow name."""
    return "startup_validation"
