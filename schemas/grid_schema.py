"""Structured grid creation schema.

Only straight grids are supported. Coordinates are Revit internal units and
should be three-number lists: [x, y, z].
"""

from tools.validators import validate_grid_data


GRID_SCHEMA = {
    "required": ["name", "start", "end"],
    "fields": {
        "name": "str",
        "start": "point3",
        "end": "point3",
    },
}


def validate(data, existing_names=None):
    """Validate create_grid payload data against the grid schema."""
    return validate_grid_data(data, existing_names)
