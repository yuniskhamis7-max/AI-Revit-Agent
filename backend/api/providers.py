# -*- coding: utf-8 -*-
"""
Providers API — Routes for reading and updating Gemini provider configuration.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from config import get_settings
from infra.db import Database
from providers import list_providers, list_providers_with_dynamic_models, get_provider

router = APIRouter(prefix="/api/providers", tags=["providers"])

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class ProviderUpdate(BaseModel):
    api_key: str | None = None
    active_model: str | None = None
    active: bool | None = None

class ProviderOut(BaseModel):
    name: str
    label: str
    models: list[str]
    configured: bool
    active: bool
    active_model: str | None = None

    class Config:
        from_attributes = True

# Dependency to get Database client from application state
def get_db(request: Request) -> Database:
    return request.app.state.db

# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProviderOut])
async def list_configured_providers(db: Database = Depends(get_db)):
    """List supported AI providers enriched with their DB config state."""
    settings = get_settings()

    cfg = await db.get_provider_config("gemini")
    db_key = cfg.get("api_key") if cfg else None
    env_key = getattr(settings, "gemini_api_key", "")
    has_key = bool(db_key or env_key)

    static_providers = list_providers_with_dynamic_models(api_key=db_key or env_key or None)

    output = []
    for p in static_providers:
        name = p["name"]
        is_active = cfg.get("active") if cfg else True
        output.append(ProviderOut(
            name=name,
            label=p["label"],
            models=p["models"],
            configured=has_key,
            active=bool(is_active),
            active_model=cfg.get("active_model") if cfg else settings.default_model,
        ))
    return output

@router.get("/models", response_model=list[ProviderOut])
async def list_provider_models(db: Database = Depends(get_db)):
    """Re-fetch models from providers and return the updated list."""
    settings = get_settings()

    cfg = await db.get_provider_config("gemini")
    db_key = cfg.get("api_key") if cfg else None
    env_key = getattr(settings, "gemini_api_key", "")
    has_key = bool(db_key or env_key)

    static_providers = list_providers_with_dynamic_models(api_key=db_key or env_key or None)

    output = []
    for p in static_providers:
        name = p["name"]
        is_active = cfg.get("active") if cfg else True
        output.append(ProviderOut(
            name=name,
            label=p["label"],
            models=p["models"],
            configured=has_key,
            active=bool(is_active),
            active_model=cfg.get("active_model") if cfg else settings.default_model,
        ))
    return output

@router.get("/{provider_name}/key")
async def get_masked_key(
    provider_name: str,
    db: Database = Depends(get_db),
):
    """Return a masked version of the stored API key for the given provider."""
    if provider_name.lower() != "gemini":
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_name}'.")

    cfg = await db.get_provider_config("gemini")
    settings = get_settings()
    raw_key = (cfg.get("api_key") if cfg and cfg.get("api_key")
               else getattr(settings, "gemini_api_key", "") or "")

    if not raw_key:
        return {"masked_key": None}

    if len(raw_key) <= 12:
        masked = raw_key[:3] + "\u2022" * (len(raw_key) - 6) + raw_key[-3:]
    else:
        masked = raw_key[:6] + "\u2022\u2022\u2022\u2022\u2022\u2022" + raw_key[-4:]

    return {"masked_key": masked}

@router.put("/{provider_name}", response_model=ProviderOut)
async def update_provider(
    provider_name: str,
    body: ProviderUpdate,
    db: Database = Depends(get_db),
):
    """Create or update provider configuration."""
    if provider_name.lower() != "gemini":
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_name}'.")

    settings = get_settings()

    # Get current config
    cfg = await db.get_provider_config("gemini")
    current_key = cfg.get("api_key") if cfg else None
    current_model = cfg.get("active_model") if cfg else settings.default_model
    current_active = cfg.get("active") if cfg else True

    new_key = body.api_key if body.api_key is not None else current_key
    new_model = body.active_model if body.active_model is not None else current_model
    new_active = body.active if body.active is not None else current_active

    if body.api_key:
        try:
            provider_instance = get_provider(
                "gemini",
                api_key=body.api_key,
                model=new_model or settings.default_model,
            )
            if not provider_instance.validate_api_key(body.api_key):
                raise HTTPException(
                    status_code=422,
                    detail="API key format is invalid for Gemini.",
                )
        except ValueError:
            pass

    await db.save_provider_config(
        provider="gemini",
        api_key=new_key or "",
        active_model=new_model or "",
        active=bool(new_active)
    )

    static = next(p for p in list_providers() if p["name"] == "gemini")
    env_key = getattr(settings, "gemini_api_key", "")
    return ProviderOut(
        name="gemini",
        label=static["label"],
        models=static["models"],
        configured=bool(new_key or env_key),
        active=bool(new_active),
        active_model=new_model,
    )
