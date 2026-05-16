"""Direct Revit level interactions.

This module contains only Revit API calls for levels. Workflow sequencing and
data validation stay outside this layer.
"""

from Autodesk.Revit.DB import FilteredElementCollector, Level

from revit.transactions import run_in_transaction

def list_level_names(document):
    """Return existing level names from the active Revit document."""
    return [level.Name for level in FilteredElementCollector(document).OfClass(Level)]


def create_level(document, name, elevation):
    """Create one Revit level when its name does not already exist."""
    if has_duplicate_name(name, list_level_names(document)):
        return {
            "success": False,
            "message": "Level already exists: {}".format(name),
            "element_id": None,
        }

    def action():
        level = Level.Create(document, elevation)
        level.Name = name
        return {
            "success": True,
            "message": "Created level: {}".format(name),
            "element_id": level.Id.IntegerValue,
        }

    return run_in_transaction(document, "Create Level {}".format(name), action)


def has_duplicate_name(name, existing_names):
    """Return True when name already exists in a case-insensitive list."""
    if not name:
        return False
    return name.strip().lower() in [existing.strip().lower() for existing in existing_names]
