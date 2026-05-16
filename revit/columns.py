"""Direct Revit column interactions.

This module is intentionally tiny. The runtime owns validation and sequencing;
the Revit layer only places one simple structural column at a point.
"""

from Autodesk.Revit.DB import BuiltInCategory, BuiltInParameter, FilteredElementCollector, FamilySymbol, Level, XYZ
from Autodesk.Revit.DB.Structure import StructuralType

from revit.transactions import run_in_transaction

def create_column(document, location, base_level, top_level, family_name, type_name):
    """Place one simple structural column using a family/type hint."""
    base = _find_level(document, base_level)
    top = _find_level(document, top_level)
    symbol = _find_symbol(document, family_name, type_name)

    if not base:
        return _failure("Column base level does not exist: {}".format(base_level))
    if not top:
        return _failure("Column top level does not exist: {}".format(top_level))
    if not symbol:
        return _failure("Column family/type was not found: {} / {}".format(family_name, type_name))

    def action():
        if not symbol.IsActive:
            symbol.Activate()
            document.Regenerate()
        column = document.Create.NewFamilyInstance(_to_xyz(location), symbol, base, StructuralType.Column)
        top_param = column.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)
        if top_param:
            top_param.Set(top.Id)
        return {
            "success": True,
            "message": "Created column: {} / {}".format(family_name, type_name),
            "element_id": column.Id.IntegerValue,
        }

    return run_in_transaction(document, "Create Column", action)


def _find_level(document, name):
    """Find a Revit level by name."""
    for level in FilteredElementCollector(document).OfClass(Level):
        if has_duplicate_name(name, [level.Name]):
            return level
    return None


def _find_symbol(document, family_name, type_name):
    """Find the requested structural column type."""
    symbols = (
        FilteredElementCollector(document)
        .OfClass(FamilySymbol)
        .OfCategory(BuiltInCategory.OST_StructuralColumns)
    )
    for symbol in symbols:
        if has_duplicate_name(family_name, [symbol.Family.Name]) and has_duplicate_name(type_name, [symbol.Name]):
            return symbol
    return None


def _to_xyz(point):
    """Convert a simple coordinate list into a Revit XYZ point."""
    return XYZ(point[0], point[1], point[2])


def _failure(message):
    """Return a small Revit operation failure."""
    return {
        "success": False,
        "message": message,
        "element_id": None,
    }


def has_duplicate_name(name, existing_names):
    """Return True when name already exists in a case-insensitive list."""
    if not name:
        return False
    return name.strip().lower() in [existing.strip().lower() for existing in existing_names]
