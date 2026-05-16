"""Pure conversion helpers.

Converters in this module should stay deterministic and independent from
pyRevit or Revit API runtime state.
"""


def to_text(value):
    """Convert a value to text for future safe display or logging."""
    if value is None:
        return ""
    return str(value)
