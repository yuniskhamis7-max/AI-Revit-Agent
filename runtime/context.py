"""Runtime context placeholder.

Context will eventually carry safe runtime metadata between orchestration
steps. It intentionally has no Revit API dependencies.
"""


def create_context():
    """Create a minimal deterministic runtime context."""
    return {
        "workflow": "startup_validation",
        "status": "initialized",
    }
