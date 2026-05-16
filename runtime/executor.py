"""Runtime executor for pyRevit command execution.

The executor owns the human-in-the-loop instruction flow: interpret, inspect,
edit, validate, approve, execute, and visualize structured payload results.
"""

from app.main import bootstrap
from interpreter.parser import parse_instruction
from interpreter.translator import translate
from revit.document import get_active_document
from revit.ui import (
    ask_for_instruction,
    confirm_payload_edit,
    confirm_payload_execution,
    edit_payload_text,
    preview_payload_text,
    show_execution_result,
    show_validation_errors,
)
from runtime.workflow import execute_payloads, has_validation_errors, validate_payloads
from tools.payload_loader import (
    parse_payload_text,
    payload_to_text,
)


INVALID_EDITED_PAYLOAD = object()
INVALID_SOURCE_PAYLOAD = object()


def run():
    """Run the phase-five controlled instruction and payload console."""
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
    """Collect one instruction, inspect payloads, approve, and execute."""
    payload = _payload_from_instruction(logger)
    if payload is INVALID_SOURCE_PAYLOAD:
        return _validation_failed("Could not create payload from instruction.")
    if payload is None:
        return _cancelled("Payload execution cancelled.")

    return _review_validate_approve_execute(logger, payload)


def _payload_from_instruction(logger):
    """Parse deterministic language and translate it into payloads."""
    instruction = ask_for_instruction()
    if not instruction:
        logger.info("Instruction entry cancelled.")
        return None

    logger.info("User instruction: {}".format(instruction))
    parsed = parse_instruction(instruction)
    logger.info("Interpretation result: {}".format(parsed))
    if not parsed["success"]:
        logger.error("Interpretation failure: {}".format(parsed["error"]))
        show_validation_errors([_result(False, "instruction", parsed["error"], "interpretation_failed")])
        return INVALID_SOURCE_PAYLOAD

    translated = translate(parsed)
    logger.info("Generated payloads: {}".format(translated))
    if not translated["success"]:
        logger.error("Translation failure: {}".format(translated["error"]))
        show_validation_errors([_result(False, "instruction", translated["error"], "translation_failed")])
        return INVALID_SOURCE_PAYLOAD

    return translated["payloads"]


def _review_validate_approve_execute(logger, payload):
    """Inspect, optionally edit, validate, approve, and execute payloads."""
    payload = _inspect_payload(logger, payload)
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
