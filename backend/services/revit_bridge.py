# -*- coding: utf-8 -*-
"""
Revit Bridge Service — HTTP client for the C# BridgeServer running on Revit.

Encapsulated in the RevitBridgeClient class.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Schema snapshot path — written on every tool discovery for debugging
_SCHEMA_SNAPSHOT_PATH = Path(__file__).parent.parent / "schemas" / "tools.json"


class RevitBridgeClient:
    """
    HTTP client for the C# BridgeServer running inside Autodesk Revit.

    Manages connection sessions, checks health, discovers tool schemas,
    and forwards tool executions to Revit.
    """
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.client: httpx.AsyncClient | None = None
        self.discovery_url = f"{self.host}:{self.port}/tools/"
        self.execute_url = f"{self.host}:{self.port}/execute/"

    async def start(self) -> None:
        """Initialize the shared HTTP client session."""
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)
            logger.debug("RevitBridgeClient session started.")

    async def stop(self) -> None:
        """Close the shared HTTP client session."""
        if self.client is not None:
            await self.client.aclose()
            self.client = None
            logger.debug("RevitBridgeClient session closed.")

    def _get_client(self) -> httpx.AsyncClient:
        """Returns the client, creating a fallback if called before start()."""
        if self.client is None:
            logger.warning(
                "HTTP client requested before start() was called. "
                "Creating a temporary fallback client."
            )
            return httpx.AsyncClient(timeout=30.0)
        return self.client

    async def check_health(self) -> bool:
        """
        Returns True if the Revit bridge is reachable and responding.
        Never raises — always returns a boolean.
        """
        try:
            client = self._get_client()
            response = await client.get(self.discovery_url, timeout=3.0)
            return response.status_code == 200
        except Exception:
            return False

    async def discover_tools(self) -> list[dict]:
        """
        Calls GET /tools/ on the Revit bridge and returns the raw tool schema list.
        Raises RuntimeError on failure.
        Side effect: writes schemas/tools.json snapshot on every successful discovery.
        """
        try:
            client = self._get_client()
            response = await client.get(self.discovery_url, timeout=15.0)
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
            raise RuntimeError(
                f"Cannot reach Revit bridge at {self.discovery_url}. "
                "Ensure Revit is running and the bridge button has been clicked."
            ) from exc

    async def execute_tool(self, tool_name: str, tool_input: dict[str, Any], timeout: int = 120) -> dict:
        """
        Sends a POST /execute/ request to the Revit bridge for a named tool.

        Payload format:
            {"tool": "<name>", "input": {<args>}}

        Returns the parsed JSON response dict.
        """
        payload = {"tool": tool_name, "input": tool_input}
        logger.debug("Bridge execute: tool=%s args=%s", tool_name, json.dumps(tool_input))

        try:
            client = self._get_client()
            response = await client.post(
                self.execute_url,
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
