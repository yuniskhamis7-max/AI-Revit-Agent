"""Direct Revit grid helper used by the Create Grids button."""

from Autodesk.Revit.DB import (
    FilteredElementCollector,
    Grid as RevitGrid,
    Line,
    Transaction,
    TransactionStatus,
    XYZ,
)


UNIT_TO_FEET = {
    "ft": 1.0,
    "feet": 1.0,
    "foot": 1.0,
    "mm": 1.0 / 304.8,
    "millimeter": 1.0 / 304.8,
    "millimeters": 1.0 / 304.8,
    "cm": 1.0 / 30.48,
    "centimeter": 1.0 / 30.48,
    "centimeters": 1.0 / 30.48,
    "m": 1.0 / 0.3048,
    "meter": 1.0 / 0.3048,
    "meters": 1.0 / 0.3048,
}


class Grid(object):
    """Small wrapper for creating a named straight Revit grid."""

    def __init__(self, document, name):
        self.document = document
        self.name = name

    def create_straight(self, start_pt, end_pt, unit="ft"):
        """Create one straight grid from start/end coordinates."""
        if _has_duplicate_name(self.name, _list_grid_names(self.document)):
            return {
                "success": False,
                "message": "Grid already exists: {}".format(self.name),
                "element_id": None,
            }

        factor = _unit_factor(unit)
        transaction = Transaction(self.document, "Create Grid {}".format(self.name))

        try:
            transaction.Start()
            line = Line.CreateBound(_to_xyz(start_pt, factor), _to_xyz(end_pt, factor))
            grid = RevitGrid.Create(self.document, line)
            grid.Name = self.name
            transaction.Commit()
            return {
                "success": True,
                "message": "Created grid: {}".format(self.name),
                "element_id": grid.Id.IntegerValue,
            }
        except Exception as error:
            if transaction.GetStatus() == TransactionStatus.Started:
                transaction.RollBack()
            return {
                "success": False,
                "message": str(error),
                "element_id": None,
            }


def _list_grid_names(document):
    return [grid.Name for grid in FilteredElementCollector(document).OfClass(RevitGrid)]


def _to_xyz(point, factor):
    return XYZ(point[0] * factor, point[1] * factor, point[2] * factor)


def _unit_factor(unit):
    normalized_unit = (unit or "ft").strip().lower()
    if normalized_unit not in UNIT_TO_FEET:
        raise ValueError("Unsupported grid unit: {}".format(unit))
    return UNIT_TO_FEET[normalized_unit]


def _has_duplicate_name(name, existing_names):
    if not name:
        return False
    normalized_name = name.strip().lower()
    return normalized_name in [existing.strip().lower() for existing in existing_names]
