"""Direct pyRevit document access.

Document access belongs in the Revit layer so runtime orchestration does not
import pyRevit or low-level Revit API modules directly.
"""

from pyrevit import revit


def get_active_document():
    """Return the active Revit document for the current pyRevit command."""
    return revit.doc
