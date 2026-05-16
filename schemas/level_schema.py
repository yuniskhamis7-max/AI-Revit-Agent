"""Structured level creation schema.

Schemas define the payload data shape future AI outputs must match before the
runtime dispatcher can execute deterministic Revit tools.
"""

from tools.validators import validate_level_data


LEVEL_SCHEMA = {
    "required": ["name", "elevation"],
    "fields": {
        "name": "str",
        "elevation": "number",
    },
}


def validate(data, existing_names=None):
    """Validate create_level payload data against the level schema."""
    return validate_level_data(data, existing_names)
