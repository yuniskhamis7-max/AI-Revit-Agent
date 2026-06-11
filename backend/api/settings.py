# -*- coding: utf-8 -*-
"""
Settings API — Key/value store for app-level frontend preferences and Revit bridge status.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from config import get_settings
from infra.db import Database
from services.revit_bridge import RevitBridgeClient
from services.tool_registry import registry

logger = logging.getLogger(__name__)

# Track whether bridge was last seen connected (for auto-recovery)
_bridge_was_connected: bool = False

router = APIRouter(tags=["settings"])

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class SettingsPayload(BaseModel):
    settings: dict[str, str]

# Dependency to get Database client from application state
def get_db(request: Request) -> Database:
    return request.app.state.db

# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/settings", response_model=dict)
async def get_settings_all(db: Database = Depends(get_db)):
    """Retrieve all stored application settings as a flat dictionary."""
    return await db.get_all_settings()

@router.put("/api/settings", response_model=dict)
async def upsert_settings(body: SettingsPayload, db: Database = Depends(get_db)):
    """Bulk insert or update application settings."""
    await db.upsert_settings(body.settings)
    return body.settings

@router.get("/api/revit/status")
async def revit_status(request: Request):
    """Lightweight Revit bridge health check with automatic tool re-discovery."""
    global _bridge_was_connected
    bridge: RevitBridgeClient = request.app.state.revit_bridge
    connected = await bridge.check_health()

    # Auto-recover: re-discover tools when bridge comes back online
    if connected and not _bridge_was_connected:
        try:
            schemas = await bridge.discover_tools()
            registry.load(schemas, bridge)
            logger.info("Bridge reconnected — reloaded %d tools.", len(schemas))
        except Exception as exc:
            logger.warning("Bridge reconnected but tool re-discovery failed: %s", exc)

    _bridge_was_connected = connected
    return {"connected": connected, "tool_count": len(registry.schemas)}

@router.post("/api/revit/refresh-tools")
async def refresh_tools(request: Request):
    """Force a fresh tool discovery from the Revit bridge."""
    try:
        bridge: RevitBridgeClient = request.app.state.revit_bridge
        schemas = await bridge.discover_tools()
        registry.load(schemas, bridge)
        logger.info("Manual tool refresh: loaded %d tools.", len(schemas))
        return {
            "status": "success",
            "tool_count": len(schemas),
            "tools": [s["name"] for s in schemas],
        }
    except Exception as exc:
        logger.error("Manual tool refresh failed: %s", exc)
        return {"status": "error", "message": str(exc), "tool_count": 0}
