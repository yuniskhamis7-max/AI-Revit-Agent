"""Pure validation helpers.

Validators in this module should not import pyRevit or Revit API modules.
"""


def is_non_empty_text(value):
    """Return True when value is a non-empty text value."""
    return isinstance(value, str) and bool(value.strip())
