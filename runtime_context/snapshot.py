"""Runtime context snapshot builder.

Snapshots are compact, serializable model-state objects. Runtime and future AI
systems should reason from these snapshots instead of live Revit API objects.
"""

from runtime_context.readers import read_document_name, read_grids, read_levels, read_project_units


def create_snapshot(document):
    """Create a read-only structured snapshot of the active Revit document."""
    levels = read_levels(document)
    grids = read_grids(document)

    return {
        "document": {
            "name": read_document_name(document),
        },
        "units": read_project_units(document),
        "levels": levels,
        "grids": grids,
        "summary": {
            "level_count": len(levels),
            "grid_count": len(grids),
        },
    }


def level_names(snapshot):
    """Return level names from a context snapshot."""
    return [level["name"] for level in snapshot.get("levels", [])]


def grid_names(snapshot):
    """Return grid names from a context snapshot."""
    return [grid["name"] for grid in snapshot.get("grids", [])]
