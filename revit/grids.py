"""Direct Revit grid interactions.

This module contains only Revit API calls for grids. For phase two, only
straight grids are supported.
"""

from Autodesk.Revit.DB import FilteredElementCollector, Grid, Line, XYZ

from revit.transactions import run_in_transaction
from tools.validators import has_duplicate_name


def list_grid_names(document):
    """Return existing grid names from the active Revit document."""
    return [grid.Name for grid in FilteredElementCollector(document).OfClass(Grid)]


def create_grid(document, name, start, end):
    """Create one straight Revit grid when its name does not already exist."""
    if has_duplicate_name(name, list_grid_names(document)):
        return {
            "success": False,
            "message": "Grid already exists: {}".format(name),
            "element_id": None,
        }

    def action():
        line = Line.CreateBound(_to_xyz(start), _to_xyz(end))
        grid = Grid.Create(document, line)
        grid.Name = name
        return {
            "success": True,
            "message": "Created grid: {}".format(name),
            "element_id": grid.Id.IntegerValue,
        }

    return run_in_transaction(document, "Create Grid {}".format(name), action)


def _to_xyz(point):
    """Convert a simple coordinate list into a Revit XYZ point."""
    return XYZ(point[0], point[1], point[2])
