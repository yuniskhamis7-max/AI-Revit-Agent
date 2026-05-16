"""Deterministic natural-language parser.

Parsing is intentionally controlled and explicit. Ambiguous language returns an
error so runtime execution only receives clear structured intent.
"""

import re

from interpreter import patterns


try:
    TEXT_TYPES = (basestring,)
except NameError:
    TEXT_TYPES = (str,)


def parse_instruction(text):
    """Parse one user instruction into a structured interpretation result."""
    cleaned = _clean(text)
    if not cleaned:
        return _failure("Instruction is required.")

    for parser in [_parse_levels_spaced, _parse_level_at, _parse_grid_from_to, _parse_grids_named]:
        result = parser(cleaned)
        if result["success"]:
            return result

    return _failure("Instruction is not supported or is ambiguous.")


def _parse_levels_spaced(text):
    """Parse: Create 3 levels spaced 4000 mm apart."""
    match = patterns.CREATE_LEVELS_SPACED.match(text)
    if not match:
        return _no_match()

    count = int(match.group("count"))
    spacing = float(match.group("spacing"))
    if count < 1 or spacing <= 0:
        return _failure("Level count and spacing must be positive.")

    return _success(
        {
            "type": "levels_spaced",
            "count": count,
            "spacing": spacing,
            "unit": match.group("unit") or "mm",
        }
    )


def _parse_level_at(text):
    """Parse: Create Level 1 at elevation 0."""
    match = patterns.CREATE_LEVEL_AT.match(text)
    if not match:
        return _no_match()

    return _success(
        {
            "type": "level_at",
            "name": _title(match.group("name")),
            "elevation": float(match.group("elevation")),
            "unit": match.group("unit") or "mm",
        }
    )


def _parse_grids_named(text):
    """Parse: Create grids A, B, and C."""
    match = patterns.CREATE_GRIDS_NAMED.match(text)
    if not match:
        return _no_match()
    if " from " in text.lower() or " to " in text.lower():
        return _failure("Grid coordinate instructions must match: Create grid A from 0,0 to 0,10000.")

    names = _parse_names(match.group("names"))
    if not names:
        return _failure("At least one grid name is required.")
    if not all(_is_simple_name(name) for name in names):
        return _failure("Grid names must be simple letters or numbers.")
    if len(names) == 1:
        return _failure("Single grid instructions must include coordinates.")

    return _success({"type": "grids_named", "names": names})


def _parse_grid_from_to(text):
    """Parse: Create grid A from 0,0 to 0,10000."""
    match = patterns.CREATE_GRID_FROM_TO.match(text)
    if not match:
        return _no_match()

    return _success(
        {
            "type": "grid_from_to",
            "name": match.group("name").upper(),
            "start": [float(match.group("x1")), float(match.group("y1")), 0.0],
            "end": [float(match.group("x2")), float(match.group("y2")), 0.0],
            "unit": match.group("unit") or "mm",
        }
    )


def _parse_names(text):
    """Parse comma/and separated names into uppercase grid names."""
    normalized = re.sub(r"\s*,?\s+and\s+", ",", text, flags=re.IGNORECASE)
    return [name.strip().upper() for name in normalized.split(",") if name.strip()]


def _is_simple_name(name):
    """Return True for simple grid names only."""
    return bool(re.match(r"^[A-Z0-9]+$", name))


def _clean(text):
    """Normalize whitespace and punctuation."""
    if not isinstance(text, TEXT_TYPES):
        return ""
    return " ".join(text.strip().strip(".").split())


def _title(value):
    """Return simple title-case names for generated payloads."""
    return value.strip().title()


def _success(instruction):
    """Return a structured parse success."""
    return {"success": True, "instruction": instruction, "error": None}


def _failure(message):
    """Return a structured parse failure."""
    return {"success": False, "instruction": None, "error": message}


def _no_match():
    """Return the neutral result used while trying parser patterns."""
    return {"success": False, "instruction": None, "error": None}
