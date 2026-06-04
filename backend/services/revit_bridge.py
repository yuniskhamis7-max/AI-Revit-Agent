# -*- coding: utf-8 -*-
"""
Revit Bridge Service — HTTP client for the C# BridgeServer running on :8080.

Responsibilities:
  - Discover the tool registry via GET /tools/
  - Execute individual tools via POST /execute/
  - Health-check the bridge connection
  - In DEVELOPMENT_MODE, soft-fail with empty mocks when Revit is not running
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger(__name__)

# Schema snapshot path — written on every tool discovery for debugging
_SCHEMA_SNAPSHOT_PATH = Path(__file__).parent.parent / "schemas" / "tools.json"

# ─────────────────────────────────────────────────────────────────────────────
# Shared HTTP client singleton
# ─────────────────────────────────────────────────────────────────────────────
# Created once at application startup (main.py lifespan) and closed on shutdown.
# Using a persistent client enables HTTP keep-alive to the local Revit bridge
# and avoids repeated connection setup overhead on every tool execution.
#
# NOTE: Single-process only. If the application ever runs with multiple workers
# each process will have its own client instance, which is correct behavior.

_http_client: httpx.AsyncClient | None = None


def init_http_client() -> None:
    """Create the shared HTTP client. Called once from the lifespan startup."""
    global _http_client
    _http_client = httpx.AsyncClient(timeout=30.0)
    logger.debug("Revit bridge HTTP client initialised.")


async def close_http_client() -> None:
    """Close the shared HTTP client. Called once from the lifespan shutdown."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
        logger.debug("Revit bridge HTTP client closed.")


def _get_client() -> httpx.AsyncClient:
    """Returns the shared client, creating a fallback if not yet initialised."""
    if _http_client is None:
        # Fallback: create a temporary client if called before lifespan init
        # (e.g. in tests or standalone scripts). Not ideal but safe.
        logger.warning(
            "HTTP client requested before init_http_client() was called. "
            "Creating a temporary client. Ensure init_http_client() is called at startup."
        )
        return httpx.AsyncClient(timeout=30.0)
    return _http_client


# ─────────────────────────────────────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────────────────────────────────────

async def check_bridge_health() -> bool:
    """
    Returns True if the Revit bridge is reachable and responding.
    Never raises — always returns a boolean.
    """
    settings = get_settings()
    try:
        client = _get_client()
        response = await client.get(settings.revit_discovery_url, timeout=3.0)
        return response.status_code == 200
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Tool Discovery
# ─────────────────────────────────────────────────────────────────────────────

async def discover_tools() -> list[dict]:
    """
    Calls GET /tools/ on the Revit bridge and returns the raw tool schema list.

    In DEVELOPMENT_MODE, if the bridge is unreachable:
      - Falls back to the cached schemas/tools.json snapshot (if available)
      - If no cache exists either, returns an empty list with a warning
    In production mode, raises on failure.

    Side effect: writes schemas/tools.json snapshot on every successful discovery.
    """
    settings = get_settings()
    try:
        client = _get_client()
        response = await client.get(settings.revit_discovery_url, timeout=15.0)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "success":
            raise RuntimeError(f"Bridge returned error: {data.get('message')}")

        schemas: list[dict] = data.get("tools", [])
        logger.info("Tool discovery: found %d tool(s): %s", len(schemas), [s["name"] for s in schemas])

        # Persist snapshot
        _SCHEMA_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SCHEMA_SNAPSHOT_PATH.write_text(json.dumps(schemas, indent=2), encoding="utf-8")
        logger.debug("Schema snapshot written -> %s", _SCHEMA_SNAPSHOT_PATH)

        return schemas

    except Exception as exc:
        if settings.development_mode:
            # ── Fallback: load from cached snapshot if available ────────────
            cached = _load_cached_schemas()
            if cached:
                logger.warning(
                    "Bridge unreachable (%s). Loaded %d tool(s) from cached snapshot.",
                    exc, len(cached),
                )
                return cached

            logger.warning(
                "Bridge unreachable during tool discovery (%s). "
                "No cached schemas available. Running with empty tool set (DEVELOPMENT_MODE=true).",
                exc,
            )
            return []
        raise RuntimeError(
            f"Cannot reach Revit bridge at {settings.revit_discovery_url}. "
            "Ensure Revit is running and the bridge button has been clicked."
        ) from exc


def _load_cached_schemas() -> list[dict]:
    """
    Loads tool schemas from the on-disk snapshot (schemas/tools.json).
    Returns the cached list, or [] if the file doesn't exist or is invalid.
    """
    if not _SCHEMA_SNAPSHOT_PATH.exists():
        return []
    try:
        raw = _SCHEMA_SNAPSHOT_PATH.read_text(encoding="utf-8")
        schemas = json.loads(raw)
        if isinstance(schemas, list) and len(schemas) > 0:
            logger.debug("Loaded %d cached tool schema(s) from %s", len(schemas), _SCHEMA_SNAPSHOT_PATH)
            return schemas
    except Exception as exc:
        logger.warning("Failed to read cached schemas from %s: %s", _SCHEMA_SNAPSHOT_PATH, exc)
    return []


# ─────────────────────────────────────────────────────────────────────────────
# Tool Execution
# ─────────────────────────────────────────────────────────────────────────────

async def execute_tool(tool_name: str, tool_input: dict[str, Any], timeout: int = 120) -> dict:
    """
    Sends a POST /execute/ request to the Revit bridge for a named tool.

    Payload format (matches the C# BridgeServer expectation):
        {"tool": "<name>", "input": {<args>}}

    Returns the parsed JSON response dict. On network failure:
      - DEVELOPMENT_MODE=true → returns a mock error dict (no crash)
      - DEVELOPMENT_MODE=false → returns an error dict with full details
    """
    settings = get_settings()
    payload = {"tool": tool_name, "input": tool_input}

    logger.debug("Bridge execute: tool=%s args=%s", tool_name, json.dumps(tool_input))

    try:
        client = _get_client()
        response = await client.post(
            settings.revit_execute_url,
            json=payload,
            timeout=float(timeout),
        )
        response.raise_for_status()
        result = response.json()
        logger.debug("Bridge response: %s", json.dumps(result))
        return result

    except Exception as exc:
        error_msg = (
            f"Bridge communication failure running tool '{tool_name}' "
            f"with input {json.dumps(tool_input)}. Error: {exc}"
        )
        logger.error(error_msg)
        return {"status": "error", "message": error_msg}
