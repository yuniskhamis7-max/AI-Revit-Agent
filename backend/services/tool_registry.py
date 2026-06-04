# -*- coding: utf-8 -*-
"""
Tool Registry Service — Manages the live tool schema discovered from the
Revit bridge and exposes typed accessors used by the AI provider adapters.

Key responsibilities:
  - Cache the raw tool schemas from bridge discovery
  - Classify tools as 'read' (fetch_*) or 'write' (everything else)
  - Build provider-agnostic tool descriptor dicts
  - Build the bridge dispatcher map (tool_name -> async callable)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from services.revit_bridge import discover_tools, execute_tool

logger = logging.getLogger(__name__)

# Minimum seconds between automatic re-discovery attempts to avoid hammering
_REDISCOVER_COOLDOWN = 5.0


# ─────────────────────────────────────────────────────────────────────────────
# Tool classification
# ─────────────────────────────────────────────────────────────────────────────

def is_read_tool(tool_name: str) -> bool:
    """
    Returns True for read-only fetch tools (auto-executed without approval).
    Convention: any tool whose name starts with 'fetch_' is a read tool.
    All other tools are write/action tools that require human approval.
    """
    return tool_name.startswith("fetch_")


def requires_approval(tool_name: str) -> bool:
    """Inverse of is_read_tool — used when building SSE events."""
    return not is_read_tool(tool_name)


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

class ToolRegistry:
    """
    Holds the tool schemas and dispatcher map for a single server lifetime.

    The registry is populated once at startup (via load()) and then read-only.
    It is intentionally a plain class (not a singleton module global) so it
    can be injected as a FastAPI dependency and easily replaced in tests.
    """

    def __init__(self) -> None:
        self._schemas: list[dict] = []
        self._dispatcher_map: dict[str, Callable[..., Any]] = {}
        self._loaded: bool = False
        self._last_discover_attempt: float = 0.0

    def load(self, schemas: list[dict]) -> None:
        """
        Populate the registry from the raw schema list returned by discover_tools().
        Builds the dispatcher map in the same pass.
        """
        self._schemas = schemas
        self._dispatcher_map = {
            schema["name"]: _make_dispatcher(schema["name"])
            for schema in schemas
        }
        self._loaded = True
        logger.info(
            "ToolRegistry loaded %d tools (%d read, %d write)",
            len(schemas),
            sum(1 for s in schemas if is_read_tool(s["name"])),
            sum(1 for s in schemas if not is_read_tool(s["name"])),
        )

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def schemas(self) -> list[dict]:
        """Raw tool schema list (as returned by the bridge)."""
        return self._schemas

    async def ensure_loaded(self, force: bool = False) -> bool:
        """
        If the registry is empty or was loaded with 0 tools (or force=True),
        attempt to re-discover tools from the Revit bridge.
        Returns True if tools are now available.

        Respects a cooldown to avoid hammering the bridge on every request.
        """
        # Skip only if we have actual tools loaded (not just an empty discovery)
        if self._loaded and self._schemas and not force:
            return True

        now = time.monotonic()
        if not force and (now - self._last_discover_attempt) < _REDISCOVER_COOLDOWN:
            return bool(self._schemas)

        self._last_discover_attempt = now
        logger.info(
            "ToolRegistry.ensure_loaded: attempting tool re-discovery from bridge... "
            "(loaded=%s, tools=%d, force=%s)",
            self._loaded, len(self._schemas), force,
        )

        try:
            schemas = await discover_tools()
            if schemas:
                self.load(schemas)
                logger.info(
                    "ToolRegistry re-discovered %d tools — registry is now live.",
                    len(schemas),
                )
                return True
            else:
                logger.warning(
                    "ToolRegistry re-discovery returned 0 tools. "
                    "Ensure Revit is running and the bridge button has been clicked."
                )
                return False
        except Exception as exc:
            logger.warning("ToolRegistry re-discovery failed: %s", exc)
            return False

    def get_dispatcher(self, tool_name: str) -> Callable | None:
        """Returns the async dispatch callable for a tool, or None if not found."""
        return self._dispatcher_map.get(tool_name)

    def tool_names(self) -> list[str]:
        return list(self._dispatcher_map.keys())

    def read_tools(self) -> list[dict]:
        return [s for s in self._schemas if is_read_tool(s["name"])]

    def write_tools(self) -> list[dict]:
        return [s for s in self._schemas if not is_read_tool(s["name"])]


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher factory
# ─────────────────────────────────────────────────────────────────────────────

def _make_dispatcher(tool_name: str) -> Callable[..., Any]:
    """
    Returns an async callable that executes the named tool via the bridge.
    Each closure captures tool_name to avoid the classic late-binding bug.
    """
    async def dispatcher(**kwargs: Any) -> dict:
        logger.info("Executing tool '%s' with args: %s", tool_name, kwargs)
        result = await execute_tool(tool_name, kwargs)
        logger.debug("Tool '%s' result: %s", tool_name, result)
        return result

    dispatcher.__name__ = tool_name
    return dispatcher


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton — shared across the app lifetime
# ─────────────────────────────────────────────────────────────────────────────

# Initialised as empty; populated in main.py lifespan before routes are served.
registry = ToolRegistry()
