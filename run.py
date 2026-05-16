"""Small shared workflow for the pyRevit buttons.

The AI only creates JSON data. This module validates that data and calls
deterministic Revit functions, so model reasoning never controls Revit directly.
"""

import json
import logging
import os

from ai.parser import parse_instruction
from revit.columns import create_column
from revit.grids import create_grid, list_grid_names
from revit.levels import create_level, list_level_names
from revit.ui import ask_for_instruction, confirm_payload_execution, preview_payload_text


PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
PAYLOAD_FILE = os.path.join(PROJECT_ROOT, "payload.json")
LOG_FILE = os.path.join(PROJECT_ROOT, "logs", "runtime", "ai_revit_agent.log")

try:
    TEXT_TYPES = (basestring,)
except NameError:
    TEXT_TYPES = (str,)


def generate_payload():
    """Generate and preview a reusable payload without executing Revit."""
    result = _build_payload()
    if result["success"]:
        preview_payload_text(_to_text(result["payload"]))
    return result


def run_category(document, category):
    """Load the active payload and execute only one selected category."""
    logger = _logger()
    load_result = _load_payload()
    if not load_result["success"]:
        return _failure("Payload load failed: {}".format(load_result["error"]), [])

    payload = load_result["payload"]
    errors = [item for item in _validate_category(document, payload, category) if not item["success"]]
    if errors:
        logger.error("{} validation failed: {}".format(category, errors))
        return _failure("{} validation failed.".format(category.title()), errors)

    preview_payload_text(_to_text({category: payload.get(category, [])}))
    if not confirm_payload_execution(category):
        logger.info("{} execution cancelled.".format(category))
        return _failure("{} execution cancelled.".format(category.title()), [])

    results = _execute_category(document, payload, category)
    logger.info("{} execution results: {}".format(category, results))
    return _summary(category, results)


def _build_payload():
    """Ask for an instruction, let AI structure it, then save it."""
    logger = _logger()
    instruction = ask_for_instruction()
    if not instruction:
        return _failure("Instruction cancelled.", [])

    logger.info("User instruction: {}".format(instruction))
    ai_result = parse_instruction(instruction)
    if not ai_result["success"]:
        logger.error("AI parsing failed: {}".format(ai_result["error"]))
        return _failure("AI parsing failed: {}".format(ai_result["error"]), [])

    save_result = _save_payload(ai_result["payload"])
    if not save_result["success"]:
        logger.error("Payload save failed: {}".format(save_result["error"]))
        return _failure("Payload save failed: {}".format(save_result["error"]), [])

    logger.info("AI generated payload: {}".format(ai_result["payload"]))
    return {"success": True, "payload": ai_result["payload"], "message": "Payload generated.", "results": []}


def _validate_category(document, payload, category):
    """Validate only the selected category."""
    error = _validate_payload(payload)
    if error:
        return [_result(False, category, error, "validation_failed")]
    if category == "levels":
        return _validate_levels(document, payload["levels"])
    if category == "grids":
        return _validate_grids(document, payload["grids"])
    if category == "columns":
        return _validate_columns(document, payload["columns"])
    return [_result(False, category, "Unsupported category: {}".format(category), "unsupported_category")]


def _execute_category(document, payload, category):
    """Execute only the selected category."""
    if category == "levels":
        return [_level_result(create_level(document, item["name"], item["elevation"])) for item in payload["levels"]]
    if category == "grids":
        return [_grid_result(create_grid(document, item["name"], item["start"], item["end"])) for item in payload["grids"]]
    if category == "columns":
        return [_column_result(document, item) for item in payload["columns"]]
    return [_result(False, category, "Unsupported category: {}".format(category), "unsupported_category")]


def _validate_payload(payload):
    """Validate the root payload shape."""
    if not isinstance(payload, dict):
        return "Payload must be a dictionary."
    for category in ["levels", "grids", "columns"]:
        if category not in payload:
            return "Payload is missing category '{}'.".format(category)
        if not isinstance(payload[category], list):
            return "Payload category '{}' must be a list.".format(category)
    return None


def _validate_levels(document, items):
    """Validate level data and duplicates."""
    if not items:
        return [_result(False, "create_level", "No level payloads were generated.", "validation_failed")]
    return _validate_named_items(items, list_level_names(document), "create_level", _validate_level)


def _validate_grids(document, items):
    """Validate grid data and duplicates."""
    if not items:
        return [_result(False, "create_grid", "No grid payloads were generated.", "validation_failed")]
    return _validate_named_items(items, list_grid_names(document), "create_grid", _validate_grid)


def _validate_columns(document, items):
    """Validate columns against existing levels."""
    if not items:
        return [_result(False, "create_column", "No column payloads were generated.", "validation_failed")]
    levels = list_level_names(document)
    return [_validation_result("create_column", _validate_column(item, levels), item, None) for item in items]


def _validate_named_items(items, existing, action, validator):
    """Validate named items while catching duplicates in one payload."""
    seen = []
    return [_validation_result(action, validator(item, existing + seen), item, seen) for item in items]


def _validate_level(data, existing_names):
    """Validate one level object."""
    if not _has_fields(data, ["name", "elevation"]):
        return "Level data is missing required fields."
    if not _text(data["name"]):
        return "Level name is required."
    if not _number(data["elevation"]):
        return "Level elevation must be a number."
    if _duplicate(data["name"], existing_names):
        return "Level already exists: {}".format(data["name"])
    return None


def _validate_grid(data, existing_names):
    """Validate one straight grid object."""
    if not _has_fields(data, ["name", "start", "end"]):
        return "Grid data is missing required fields."
    if not _text(data["name"]):
        return "Grid name is required."
    if not _point(data["start"]) or not _point(data["end"]):
        return "Grid coordinates must be three-number points."
    if data["start"] == data["end"]:
        return "Grid start and end points must be different."
    if _duplicate(data["name"], existing_names):
        return "Grid already exists: {}".format(data["name"])
    return None


def _validate_column(data, existing_level_names):
    """Validate one simple column object."""
    if not _has_fields(data, ["location", "base_level", "top_level", "family", "type"]):
        return "Column data is missing required fields."
    if not _point(data["location"]):
        return "Column location must be a three-number point."
    if data["base_level"].strip().lower() == data["top_level"].strip().lower():
        return "Column base level and top level must be different."
    for field in ["base_level", "top_level", "family", "type"]:
        if not _text(data[field]):
            return "Column {} is required.".format(field.replace("_", " "))
    if not _duplicate(data["base_level"], existing_level_names):
        return "Column base level does not exist: {}".format(data["base_level"])
    if not _duplicate(data["top_level"], existing_level_names):
        return "Column top level does not exist: {}".format(data["top_level"])
    return None


def _validation_result(action, error, item, seen):
    """Convert validation into UI results."""
    if not error and seen is not None:
        seen.append(item["name"])
    return _result(error is None, action, error or "Payload is valid.", "validation_failed" if error else None)


def _column_result(document, item):
    """Execute one validated column item."""
    result = create_column(document, item["location"], item["base_level"], item["top_level"], item["family"], item["type"])
    return _normalize("create_column", result)


def _level_result(result):
    """Normalize one level result."""
    return _normalize("create_level", result)


def _grid_result(result):
    """Normalize one grid result."""
    return _normalize("create_grid", result)


def _normalize(action, result):
    """Normalize Revit operation results for the UI."""
    element_id = result.get("element_id")
    return _result(result["success"], action, result["message"], None if result["success"] else result["message"], element_id)


def _load_payload():
    """Load payload.json."""
    try:
        with open(PAYLOAD_FILE, "r") as payload_file:
            return {"success": True, "payload": json.load(payload_file), "error": None}
    except Exception as error:
        return {"success": False, "payload": None, "error": str(error)}


def _save_payload(payload):
    """Save payload.json."""
    try:
        with open(PAYLOAD_FILE, "w") as payload_file:
            json.dump(payload, payload_file, indent=4, sort_keys=True)
        return {"success": True, "error": None}
    except Exception as error:
        return {"success": False, "error": str(error)}


def _logger():
    """Return the shared runtime logger."""
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger("ai_revit_agent")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE)
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)

    return logger


def _summary(category, results):
    """Summarize category execution."""
    succeeded = len([item for item in results if item["success"]])
    failed = len(results) - succeeded
    return {
        "success": failed == 0,
        "message": "{} execution completed. Succeeded: {}. Failed: {}.".format(category.title(), succeeded, failed),
        "results": results,
    }


def _failure(message, results):
    """Create a structured command failure."""
    return {"success": False, "message": message, "results": results}


def _result(success, action, message, error, element_id=None):
    """Create one validation or execution result."""
    return {
        "success": success,
        "action": action,
        "message": message,
        "error": error,
        "element_ids": [element_id] if element_id is not None else [],
    }


def _has_fields(data, fields):
    """Return True when all fields exist."""
    return isinstance(data, dict) and all(field in data for field in fields)


def _duplicate(name, existing_names):
    """Return True when name already exists in a case-insensitive list."""
    if not _text(name):
        return False
    return name.strip().lower() in [existing.strip().lower() for existing in existing_names]


def _text(value):
    """Return True for non-empty text."""
    return isinstance(value, TEXT_TYPES) and bool(value.strip())


def _number(value):
    """Return True for int/float values but not bool."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _point(value):
    """Return True for [x, y, z] numeric coordinates."""
    return isinstance(value, (list, tuple)) and len(value) == 3 and all(_number(item) for item in value)


def _to_text(payload):
    """Format payload data for preview dialogs."""
    return json.dumps(payload, indent=4, sort_keys=True)
