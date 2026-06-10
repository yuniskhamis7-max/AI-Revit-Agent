# -*- coding: utf-8 -*-
"""
Settings API — Key/value store for app-level frontend preferences.

Routes:
  GET  /api/settings        — get all settings as a dict
  PUT  /api/settings        — bulk upsert settings
  GET  /api/revit/status    — Revit bridge health check
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AppSetting
from services.revit_bridge import check_bridge_health, discover_tools
from services.tool_registry import registry

import logging

logger = logging.getLogger(__name__)

# Track whether bridge was last seen connected (for auto-recovery)
_bridge_was_connected: bool = False

router = APIRouter(tags=["settings"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class SettingsPayload(BaseModel):
    """
    Request/response body for bulk upserting application settings.

    Attributes:
        settings: Key-value dictionary of setting names to string values.
                  Keys are arbitrary identifiers (e.g. 'theme', 'sidebar_width').
    """
    settings: dict[str, str]


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/api/settings", response_model=dict)
async def get_settings_all(db: AsyncSession = Depends(get_db)):
    """
    Retrieve all stored application settings as a flat dictionary.

    Args:
        db: Injected async database session.

    Returns:
        dict[str, str]: All settings as {key: value} pairs.
    """
    result = await db.execute(select(AppSetting))
    return {row.key: row.value for row in result.scalars().all()}


@router.put("/api/settings", response_model=dict)
async def upsert_settings(body: SettingsPayload, db: AsyncSession = Depends(get_db)):
    """
    Bulk insert or update application settings.

    Existing keys are updated in place; new keys are created. Keys not
    present in the payload are left unchanged (not deleted).

    Args:
        body: Dictionary of settings to upsert.
        db:   Injected async database session.

    Returns:
        dict[str, str]: The settings that were written.
    """
    result = await db.execute(select(AppSetting))
    existing = {row.key: row for row in result.scalars().all()}

    for key, value in body.settings.items():
        if key in existing:
            existing[key].value = value
        else:
            db.add(AppSetting(key=key, value=value))

    await db.flush()
    return body.settings


@router.get("/api/revit/status")
async def revit_status():
    """
    Lightweight Revit bridge health check with automatic tool re-discovery.

    Checks whether the C# bridge is reachable. When the bridge transitions
    from disconnected to connected, automatically re-discovers available tools
    to recover from outages without manual intervention.

    Returns:
        dict: {
            'connected': bool — True if bridge responded successfully,
            'tool_count': int — Number of tools currently in the registry.
        }
    """
    global _bridge_was_connected
    connected = await check_bridge_health()

    # Auto-recover: re-discover tools when bridge comes back online
    if connected and not _bridge_was_connected:
        try:
            schemas = await discover_tools()
            registry.load(schemas)
            logger.info("Bridge reconnected — reloaded %d tools.", len(schemas))
        except Exception as exc:
            logger.warning("Bridge reconnected but tool re-discovery failed: %s", exc)

    _bridge_was_connected = connected
    return {"connected": connected, "tool_count": len(registry.schemas)}


@router.post("/api/revit/refresh-tools")
async def refresh_tools():
    """
    Force a fresh tool discovery from the Revit bridge.

    Useful when the bridge was restarted, tools were added or removed in Revit,
    or the cached registry is suspected to be stale.

    Returns:
        dict: {
            'status': 'success' | 'error',
            'tool_count': int — Number of tools discovered,
            'tools': list[str] — Names of discovered tools (on success).
        }
    """
    try:
        schemas = await discover_tools()
        registry.load(schemas)
        logger.info("Manual tool refresh: loaded %d tools.", len(schemas))
        return {
            "status": "success",
            "tool_count": len(schemas),
            "tools": [s["name"] for s in schemas],
        }
    except Exception as exc:
        logger.error("Manual tool refresh failed: %s", exc)
        return {"status": "error", "message": str(exc), "tool_count": 0}
