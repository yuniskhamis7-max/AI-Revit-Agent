"""Runtime executor for pyRevit command execution.

The executor owns the human-in-the-loop console flow: load, inspect, edit,
validate, approve, execute, and visualize structured payload results.
"""

from app.main import bootstrap
from app.config import PAYLOADS_DIR
from revit.document import get_active_document
from revit.ui import (
    confirm_payload_edit,
    confirm_payload_execution,
    edit_payload_text,
    preview_payload_text,
    select_payload_file,
    show_execution_result,
    show_validation_errors,
)
from runtime.workflow import execute_payloads, has_validation_errors, validate_payloads
from tools.payload_loader import (
    list_payload_files,
    load_payload_file,
    parse_payload_text,
    payload_to_text,
)


INVALID_EDITED_PAYLOAD = object()


def run():
    """Run the phase-four payload inspection and approval console."""
    logger = bootstrap()

    try:
        result = _run_payload_console(logger)
    except Exception as error:
        result = {"success": False, "message": str(error), "results": []}
        logger.exception("Payload console failed unexpectedly.")

    if result["success"]:
        logger.info(result["message"])
    else:
        logger.error(result["message"])

    return result


def _run_payload_console(logger):
    """Load, review, validate, approve, and execute payloads."""
    payload_path = select_payload_file(list_payload_files(PAYLOADS_DIR))
    if not payload_path:
        logger.info("Payload execution cancelled before file selection.")
        return _cancelled("Payload execution cancelled.")

    load_result = load_payload_file(payload_path)
    logger.info("Loaded payload file: {}".format(payload_path))
    if not load_result["success"]:
        result = _validation_failed(load_result["error"])
        show_validation_errors(result["results"])
        return result

    payload = _inspect_payload(logger, load_result["payload"])
    if payload is INVALID_EDITED_PAYLOAD:
        return _validation_failed("Edited payload JSON is invalid.")
    if payload is None:
        return _cancelled("Payload execution cancelled during editing.")

    logger.info("Payload ready for validation: {}".format(payload))
    document = get_active_document()
    validation_results = validate_payloads(document, payload)
    if has_validation_errors(validation_results):
        logger.error("Validation failures: {}".format(validation_results))
        show_validation_errors(validation_results)
        return _validation_failed("Payload validation failed.", validation_results)

    if not confirm_payload_execution():
        logger.info("Payload execution cancelled before approval.")
        return _cancelled("Payload execution cancelled before approval.")

    logger.info("Payload execution approved.")
    result = execute_payloads(document, payload)
    logger.info("Execution results: {}".format(result))
    show_execution_result(result)
    return result


def _inspect_payload(logger, payload):
    """Preview payload text and optionally parse user edits."""
    text = payload_to_text(payload)
    preview_payload_text(text)

    if not confirm_payload_edit():
        return payload

    edited_text = edit_payload_text(text)
    if edited_text is None:
        logger.info("Payload edit dialog cancelled.")
        return None

    logger.info("Edited payload text: {}".format(edited_text))
    parse_result = parse_payload_text(edited_text)
    if parse_result["success"]:
        return parse_result["payload"]

    logger.error("Edited payload validation failure: {}".format(parse_result["error"]))
    show_validation_errors([_result(False, "payload", parse_result["error"], "invalid_json")])
    return INVALID_EDITED_PAYLOAD


def _cancelled(message):
    """Return a structured cancellation result."""
    return {
        "success": False,
        "message": message,
        "results": [],
    }


def _validation_failed(message, results=None):
    """Return a structured validation failure result."""
    return {
        "success": False,
        "message": message,
        "results": results or [_result(False, "payload", message, "validation_failed")],
    }


def _result(success, action, message, error):
    """Create a small structured result for console-level failures."""
    return {
        "success": success,
        "action": action,
        "message": message,
        "error": error,
        "element_ids": [],
    }
