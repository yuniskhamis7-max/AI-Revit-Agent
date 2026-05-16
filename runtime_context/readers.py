"""Read-only Revit model-state readers.

Readers inspect the active document and return plain structured data. They must
never start transactions or modify the Revit model.
"""

from Autodesk.Revit.DB import FilteredElementCollector, Grid, Level


def read_document_name(document):
    """Return the active document name."""
    return document.Title


def read_levels(document):
    """Return compact structured information about existing levels."""
    return [
        {
            "id": level.Id.IntegerValue,
            "name": level.Name,
            "elevation": level.Elevation,
        }
        for level in FilteredElementCollector(document).OfClass(Level)
    ]


def read_grids(document):
    """Return compact structured information about existing grids."""
    return [
        {
            "id": grid.Id.IntegerValue,
            "name": grid.Name,
        }
        for grid in FilteredElementCollector(document).OfClass(Grid)
    ]


def read_project_units(document):
    """Return minimal project unit information."""
    return {
        "length": _read_length_unit(document),
    }


def _read_length_unit(document):
    """Return a best-effort length unit label across Revit API versions."""
    units = document.GetUnits()

    try:
        from Autodesk.Revit.DB import UnitType

        return str(units.GetFormatOptions(UnitType.UT_Length).DisplayUnits)
    except Exception:
        pass

    try:
        from Autodesk.Revit.DB import SpecTypeId

        return str(units.GetFormatOptions(SpecTypeId.Length).GetUnitTypeId())
    except Exception:
        return "unknown"
