"""Normalize AI JSON into the small payload shape."""


EMPTY_PAYLOAD = {"levels": [], "grids": [], "columns": []}


def normalize_payload(payload):
    """Return a payload with all supported category arrays present."""
    normalized = _empty_payload()
    if not isinstance(payload, dict):
        return normalized
    for category in normalized:
        if isinstance(payload.get(category), list):
            normalized[category] = payload[category]
    return normalized


def _empty_payload():
    """Create a fresh empty payload."""
    return {"levels": [], "grids": [], "columns": []}
