"""Gemini-backed instruction parser.

This module is the only place that talks to an LLM. The model produces
structured JSON data only; validation and deterministic Revit execution stay
outside the AI layer so model reasoning can never bypass safety checks.
"""

import json
import os
import socket

from ai.formatter import normalize_payload
from ai.prompts import PAYLOAD_SCHEMA, SYSTEM_PROMPT


API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_API_KEY = "AIzaSyAbupUKFeHur3kOISbMI1ABkJrgouZBp1Q"


def parse_instruction(instruction):
    """Convert natural-language instruction text into structured payload data."""
    if not instruction or not instruction.strip():
        return _failure("Instruction is required.")

    response = _call_gemini(instruction)
    if not response["success"]:
        return response

    payload = normalize_payload(response["payload"])
    return {"success": True, "payload": payload, "error": None}


def _call_gemini(instruction):
    """Send one schema-constrained request to Gemini."""
    api_key = os.environ.get("GEMINI_API_KEY") or DEFAULT_API_KEY
    if not api_key:
        return _failure("GEMINI_API_KEY is not set.")

    try:
        raw = _post_json(api_key, _request_body(instruction))
        return {"success": True, "payload": _extract_payload(raw), "error": None}
    except Exception as error:
        return _failure(_friendly_error(error))


def _request_body(instruction):
    """Build a Gemini request that asks for structured JSON only."""
    return {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": instruction}],
            },
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": PAYLOAD_SCHEMA,
        },
    }


def _post_json(api_key, body):
    """Post JSON using stdlib modules so pyRevit does not need an SDK."""
    data = json.dumps(body).encode("utf-8")
    request = _request(API_URL, data, api_key)
    response = _urlopen(request, timeout=60)
    return json.loads(response.read().decode("utf-8"))


def _extract_payload(response):
    """Extract JSON text from the Gemini response."""
    text = _candidate_text(response.get("candidates", []))
    return json.loads(text)


def _candidate_text(candidates):
    """Read text from the first Gemini candidate."""
    for candidate in candidates:
        for part in candidate.get("content", {}).get("parts", []):
            if "text" in part:
                return part["text"]
    return ""


def _failure(message):
    """Return a structured AI parsing failure."""
    return {"success": False, "payload": None, "error": message}


try:
    from urllib.error import HTTPError as _HTTPError
    from urllib.error import URLError as _URLError
    from urllib.request import Request as _Request
    from urllib.request import urlopen as _urlopen
except ImportError:
    from urllib2 import HTTPError as _HTTPError
    from urllib2 import Request as _Request
    from urllib2 import URLError as _URLError
    from urllib2 import urlopen as _urlopen


def _request(url, data, api_key):
    """Create a Python 2/3 compatible JSON request."""
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    request = _Request(url.format(model=model), data)
    request.add_header("x-goog-api-key", api_key)
    request.add_header("Content-Type", "application/json")
    return request


def _friendly_error(error):
    """Return an actionable AI connection or response error."""
    if isinstance(error, _HTTPError):
        return _http_error(error)
    if isinstance(error, _URLError):
        return _url_error(error)
    return str(error)


def _http_error(error):
    """Include Gemini response text for authentication or schema issues."""
    try:
        details = error.read().decode("utf-8")
    except Exception:
        details = str(error)
    return "Gemini API returned HTTP {}: {}".format(error.code, details)


def _url_error(error):
    """Explain network failures without exposing the API key."""
    reason = getattr(error, "reason", error)
    if _is_unreachable(reason):
        return (
            "Gemini API is unreachable from this Revit/pyRevit process. "
            "Check internet access, VPN, firewall, proxy settings, or whether "
            "generativelanguage.googleapis.com is blocked. No Revit execution was attempted."
        )
    return "Gemini API connection failed: {}".format(reason)


def _is_unreachable(reason):
    """Detect common Windows unreachable-network errors."""
    errno_value = getattr(reason, "errno", None)
    if errno_value == 10051:
        return True
    if isinstance(reason, socket.error) and reason.args and reason.args[0] == 10051:
        return True
    return "10051" in str(reason)
