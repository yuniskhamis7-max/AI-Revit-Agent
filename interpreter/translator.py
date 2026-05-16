"""Translate parsed instructions into runtime execution payloads.

Translation is separate from parsing and execution so future AI understanding
can be swapped in while deterministic payload validation remains unchanged.
"""

from runtime_context.snapshot import grid_names, level_names
from tools.validators import has_duplicate_name


MM_TO_FEET = 1.0 / 304.8
M_TO_FEET = 1.0 / 0.3048
DEFAULT_GRID_LENGTH = 10000.0
DEFAULT_GRID_SPACING = 4000.0


def translate(parsed_result, context_snapshot=None):
    """Convert a successful parse result into standardized payloads."""
    if not parsed_result["success"]:
        return _failure(parsed_result["error"])

    instruction = parsed_result["instruction"]
    instruction_type = instruction["type"]

    if instruction_type == "levels_spaced":
        payloads = _levels_spaced_payloads(instruction)
        return _context_checked_success(payloads, context_snapshot)
    if instruction_type == "level_at":
        payloads = [_level_payload(instruction["name"], instruction["elevation"], instruction["unit"])]
        return _context_checked_success(payloads, context_snapshot)
    if instruction_type == "grids_named":
        payloads = _grids_named_payloads(instruction)
        return _context_checked_success(payloads, context_snapshot)
    if instruction_type == "grid_from_to":
        payloads = [_grid_from_to_payload(instruction)]
        return _context_checked_success(payloads, context_snapshot)

    return _failure("Parsed instruction type is not supported.")


def _levels_spaced_payloads(instruction):
    """Create level payloads from count and spacing."""
    payloads = []
    for index in range(instruction["count"]):
        elevation = instruction["spacing"] * index
        payloads.append(_level_payload("Level {}".format(index + 1), elevation, instruction["unit"]))
    return payloads


def _grids_named_payloads(instruction):
    """Create simple parallel grid payloads from names."""
    payloads = []
    for index, name in enumerate(instruction["names"]):
        offset = DEFAULT_GRID_SPACING * index
        payloads.append(
            _grid_payload(
                name,
                [offset, 0.0, 0.0],
                [offset, DEFAULT_GRID_LENGTH, 0.0],
                "mm",
            )
        )
    return payloads


def _grid_from_to_payload(instruction):
    """Create one grid payload from explicit coordinates."""
    return _grid_payload(instruction["name"], instruction["start"], instruction["end"], instruction["unit"])


def _level_payload(name, elevation, unit):
    """Create a standardized create_level payload."""
    return {
        "action": "create_level",
        "data": {
            "name": name,
            "elevation": _to_feet(elevation, unit),
        },
    }


def _grid_payload(name, start, end, unit):
    """Create a standardized create_grid payload."""
    return {
        "action": "create_grid",
        "data": {
            "name": name,
            "start": _point_to_feet(start, unit),
            "end": _point_to_feet(end, unit),
        },
    }


def _point_to_feet(point, unit):
    """Convert a point from parsed units to Revit internal feet."""
    return [_to_feet(point[0], unit), _to_feet(point[1], unit), _to_feet(point[2], unit)]


def _to_feet(value, unit):
    """Convert controlled instruction units into Revit internal feet."""
    if unit == "ft":
        return value
    if unit == "m":
        return value * M_TO_FEET
    return value * MM_TO_FEET


def _context_checked_success(payloads, context_snapshot):
    """Return generated payloads or a context-aware duplicate-name failure."""
    error = _find_context_conflict(payloads, context_snapshot)
    if error:
        return _failure(error)
    return _success(payloads)


def _find_context_conflict(payloads, context_snapshot):
    """Detect generated names that already exist in the context snapshot."""
    if not context_snapshot:
        return None

    for payload in payloads:
        name = payload["data"]["name"]
        if payload["action"] == "create_level" and has_duplicate_name(name, level_names(context_snapshot)):
            return _duplicate_message("level", name, level_names(context_snapshot))
        if payload["action"] == "create_grid" and has_duplicate_name(name, grid_names(context_snapshot)):
            return _duplicate_message("grid", name, grid_names(context_snapshot))
    return None


def _duplicate_message(kind, name, existing_names):
    """Create a deterministic duplicate-name message with an alternative."""
    return "{} already exists: {}. Suggested name: {}.".format(
        kind.title(),
        name,
        _suggest_name(name, existing_names),
    )


def _suggest_name(name, existing_names):
    """Suggest the first available numbered name."""
    index = 1
    while has_duplicate_name("{} {}".format(name, index), existing_names):
        index += 1
    return "{} {}".format(name, index)


def _success(payloads):
    """Return a structured translation success."""
    return {"success": True, "payloads": payloads, "error": None}


def _failure(message):
    """Return a structured translation failure."""
    return {"success": False, "payloads": [], "error": message}
