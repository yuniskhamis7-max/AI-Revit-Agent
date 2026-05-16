"""Payload-driven runtime workflow orchestration.

The workflow layer is the internal execution language for deterministic BIM
operations. Future AI systems can produce the same small payload format while
this layer validates, dispatches, and sequences actions safely.
"""

import logging

from revit.grids import create_grid, list_grid_names
from revit.levels import create_level, list_level_names
from schemas import grid_schema, level_schema
from tools.validators import validate_payload_shape


def run_demo_workflow(document):
    """Build demo payloads and execute them through the dispatcher."""
    payloads = [
        {
            "action": "create_level",
            "data": {
                "name": "AI Test Level",
                "elevation": 10.0,
            },
        },
        {
            "action": "create_grid",
            "data": {
                "name": "AI Test Grid",
                "start": [0.0, 0.0, 0.0],
                "end": [30.0, 0.0, 0.0],
            },
        },
    ]

    return execute_payloads(document, payloads)


def execute_payloads(document, payloads):
    """Execute one payload or a list of payloads sequentially."""
    logger = logging.getLogger("ai_revit_agent")
    payload_list = _as_payload_list(payloads)
    results = []

    if not payload_list:
        result = _failure("validation_failed", "No payloads were provided.")
        _log_result(logger, result)
        return {
            "success": False,
            "message": _summary_message([result]),
            "results": [result],
        }

    for payload in payload_list:
        result = execute_payload(document, payload)
        results.append(result)

    return {
        "success": all(result["success"] for result in results),
        "message": _summary_message(results),
        "results": results,
    }


def validate_payloads(document, payloads):
    """Validate one or many payloads without executing Revit operations."""
    payload_list = _as_payload_list(payloads)
    results = []
    seen_level_names = []
    seen_grid_names = []

    if not payload_list:
        return [_failure("validation_failed", "No payloads were provided.")]

    for payload in payload_list:
        result = _validate_payload(document, payload, seen_level_names, seen_grid_names)
        results.append(result)
        _remember_valid_name(payload, seen_level_names, seen_grid_names, result)

    return results


def execute_payload(document, payload):
    """Validate and dispatch a single standardized action payload."""
    logger = logging.getLogger("ai_revit_agent")
    logger.info("Received payload: {}".format(payload))

    result = _dispatch_payload(document, payload)
    _log_result(logger, result)
    return result


def has_validation_errors(validation_results):
    """Return True when any validation result failed."""
    return any(not result["success"] for result in validation_results)


def _dispatch_payload(document, payload):
    """Route one validated payload to the supported deterministic action."""
    error = validate_payload_shape(payload)
    if error:
        return _failure("validation_failed", error)

    action = payload["action"]
    if action == "create_level":
        return _execute_create_level(document, payload["data"])
    if action == "create_grid":
        return _execute_create_grid(document, payload["data"])

    return _failure("unsupported_action", "Unsupported action: {}".format(action))


def _validate_payload(document, payload, seen_level_names, seen_grid_names):
    """Validate payload shape, action support, schema data, and duplicates."""
    error = validate_payload_shape(payload)
    if error:
        return _failure("validation_failed", error)

    action = payload["action"]
    data = payload["data"]

    if action == "create_level":
        names = list_level_names(document) + seen_level_names
        return _validation_result(action, level_schema.validate(data, names))
    if action == "create_grid":
        names = list_grid_names(document) + seen_grid_names
        return _validation_result(action, grid_schema.validate(data, names))

    return _failure("unsupported_action", "Unsupported action: {}".format(action))


def _validation_result(action, error):
    """Create a structured validation result."""
    if error:
        return _failure("validation_failed", error, action)
    return {
        "success": True,
        "action": action,
        "message": "Payload is valid.",
        "error": None,
        "element_ids": [],
    }


def _remember_valid_name(payload, seen_level_names, seen_grid_names, result):
    """Track names from valid payloads so duplicates in one batch are blocked."""
    if not result["success"]:
        return
    if payload["action"] == "create_level":
        seen_level_names.append(payload["data"]["name"])
    if payload["action"] == "create_grid":
        seen_grid_names.append(payload["data"]["name"])


def _as_payload_list(payloads):
    """Normalize one payload or many payloads into a list."""
    if isinstance(payloads, list):
        return payloads
    return [payloads]


def _execute_create_level(document, data):
    """Validate and execute a create_level action."""
    error = level_schema.validate(data, list_level_names(document))
    if error:
        return _failure("validation_failed", error, "create_level")

    result = create_level(document, data["name"], data["elevation"])
    return _normalize_result("create_level", result)


def _execute_create_grid(document, data):
    """Validate and execute a create_grid action."""
    error = grid_schema.validate(data, list_grid_names(document))
    if error:
        return _failure("validation_failed", error, "create_grid")

    result = create_grid(document, data["name"], data["start"], data["end"])
    return _normalize_result("create_grid", result)


def _normalize_result(action, result):
    """Return a consistent structured execution result."""
    element_id = result.get("element_id")
    element_ids = [element_id] if element_id is not None else []

    return {
        "success": result["success"],
        "action": action,
        "message": result["message"],
        "error": None if result["success"] else result["message"],
        "element_ids": element_ids,
    }


def _failure(error_code, message, action=None):
    """Return a consistent structured failure result."""
    return {
        "success": False,
        "action": action,
        "message": message,
        "error": error_code,
        "element_ids": [],
    }


def _summary_message(results):
    """Create a compact message for UI and logs."""
    succeeded = len([result for result in results if result["success"]])
    failed = len(results) - succeeded
    return "Payload execution completed. Succeeded: {}. Failed: {}.".format(succeeded, failed)


def _log_result(logger, result):
    """Record validation, execution success, and execution errors."""
    if result["success"]:
        logger.info("Execution success: {}".format(result["message"]))
    else:
        logger.error("Execution error: {} | {}".format(result["error"], result["message"]))
