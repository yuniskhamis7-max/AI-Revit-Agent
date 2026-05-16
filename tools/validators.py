"""Pure validation helpers.

Validators stay independent from pyRevit, Revit API, and workflow sequencing so
they can safely validate future AI-generated payload data before execution.
"""


def is_non_empty_text(value):
    """Return True when value is a non-empty text value."""
    return isinstance(value, str) and bool(value.strip())


def has_required_fields(data, required_fields):
    """Return True when all required fields are present."""
    if not isinstance(data, dict):
        return False
    return all(field in data for field in required_fields)


def has_duplicate_name(name, existing_names):
    """Return True when name already exists in a case-insensitive list."""
    if not is_non_empty_text(name):
        return False
    normalized = name.strip().lower()
    return normalized in [existing.strip().lower() for existing in existing_names]


def is_valid_elevation(value):
    """Return True when elevation is a number."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def is_valid_point3(value):
    """Return True when value is a three-number coordinate."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return False
    return all(is_valid_elevation(item) for item in value)


def validate_payload_shape(payload):
    """Validate the standard runtime payload envelope."""
    if not isinstance(payload, dict):
        return "Payload must be a dictionary."
    if not has_required_fields(payload, ["action", "data"]):
        return "Payload must include action and data."
    if not is_non_empty_text(payload["action"]):
        return "Payload action is required."
    if not isinstance(payload["data"], dict):
        return "Payload data must be a dictionary."
    return None


def validate_level_data(data, existing_names=None):
    """Validate structured level creation payload data."""
    if not has_required_fields(data, ["name", "elevation"]):
        return "Level data is missing required fields."
    if not is_non_empty_text(data["name"]):
        return "Level name is required."
    if not is_valid_elevation(data["elevation"]):
        return "Level elevation must be a number."
    if existing_names and has_duplicate_name(data["name"], existing_names):
        return "Level already exists: {}".format(data["name"])
    return None


def validate_grid_data(data, existing_names=None):
    """Validate structured straight-grid creation payload data."""
    if not has_required_fields(data, ["name", "start", "end"]):
        return "Grid data is missing required fields."
    if not is_non_empty_text(data["name"]):
        return "Grid name is required."
    if not is_valid_point3(data["start"]) or not is_valid_point3(data["end"]):
        return "Grid coordinates must be three-number points."
    if data["start"] == data["end"]:
        return "Grid start and end points must be different."
    if existing_names and has_duplicate_name(data["name"], existing_names):
        return "Grid already exists: {}".format(data["name"])
    return None
