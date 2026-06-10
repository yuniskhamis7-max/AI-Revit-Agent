# -*- coding: utf-8 -*-
"""
Providers API — Routes for reading and updating AI provider configuration.

Routes:
  GET  /api/providers            — list all providers with configured status
  PUT  /api/providers/{name}     — set API key / active model / activate provider
  GET  /api/providers/models     — list available models per provider
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db
from models import ProviderConfig
from providers import list_providers, list_providers_with_dynamic_models, get_provider

router = APIRouter(prefix="/api/providers", tags=["providers"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class ProviderUpdate(BaseModel):
    """
    Request body for updating a provider's configuration.

    All fields are optional — only provided fields are updated.

    Attributes:
        api_key:      New API key to store for this provider. Validated for format.
        active_model: Model ID to use for this provider. Rejected if it contains
                      serialisation artifacts like '[object Object]'.
        active:       If True, activates this provider and deactivates all others.
                      If False, deactivates this provider.
    """
    api_key: str | None = None
    active_model: str | None = None
    active: bool | None = None


class ProviderOut(BaseModel):
    """
    Enriched provider response returned by list and update endpoints.

    Combines static provider metadata (name, label, models) with the
    dynamic per-user configuration state from the database.

    Attributes:
        name:         Internal provider identifier (e.g. 'gemini', 'openai').
        label:        Human-readable display name (e.g. 'Google Gemini').
        models:       List of available model IDs for this provider.
        configured:   True if an API key is stored (in DB or env var).
        active:       True if this is the currently selected provider.
        active_model: Model ID currently in use for this provider, or None.
    """
    name: str
    label: str
    models: list[str]
    configured: bool       # True if an API key is stored
    active: bool
    active_model: str | None = None

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProviderOut])
async def list_configured_providers(db: AsyncSession = Depends(get_db)):
    """
    List all supported AI providers enriched with their DB config state.

    For each provider, returns whether an API key is configured, whether it
    is the active provider, and which model is currently selected. Gemini
    models are fetched dynamically from the API when a key is available.

    Args:
        db: Injected async database session.

    Returns:
        list[ProviderOut]: All supported providers with their configuration status.
    """
    settings = get_settings()

    # Try to get the Gemini API key for dynamic model fetching
    result_cfg = await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider == "gemini")
    )
    gemini_cfg = result_cfg.scalar_one_or_none()
    gemini_key = (gemini_cfg.api_key if gemini_cfg and gemini_cfg.api_key
                  else getattr(settings, "gemini_api_key", "") or None)

    static_providers = list_providers_with_dynamic_models(api_key=gemini_key)

    result = await db.execute(select(ProviderConfig))
    db_configs: dict[str, ProviderConfig] = {
        cfg.provider: cfg for cfg in result.scalars().all()
    }

    output = []
    for p in static_providers:
        name = p["name"]
        cfg = db_configs.get(name)

        # Fall back to env-var key if no DB record exists yet
        env_key = getattr(settings, f"{name}_api_key", "")
        has_key = bool((cfg and cfg.api_key) or env_key)

        output.append(ProviderOut(
            name=name,
            label=p["label"],
            models=p["models"],
            configured=has_key,
            active=cfg.active if cfg else (name == settings.default_provider),
            active_model=cfg.active_model if cfg else settings.default_model,
        ))

    return output


@router.get("/models", response_model=list[ProviderOut])
async def list_provider_models(db: AsyncSession = Depends(get_db)):
    """
    Re-fetch models from providers and return the updated list.

    Dynamically queries the Gemini API for available models (when a key is
    configured). Other providers use their static model lists. Use this
    endpoint to refresh the model dropdown in the frontend.

    Args:
        db: Injected async database session.

    Returns:
        list[ProviderOut]: All providers with their current (possibly dynamic) model lists.
    """
    settings = get_settings()

    # Get Gemini API key
    result_cfg = await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider == "gemini")
    )
    gemini_cfg = result_cfg.scalar_one_or_none()
    gemini_key = (gemini_cfg.api_key if gemini_cfg and gemini_cfg.api_key
                  else getattr(settings, "gemini_api_key", "") or None)

    static_providers = list_providers_with_dynamic_models(api_key=gemini_key)

    result = await db.execute(select(ProviderConfig))
    db_configs: dict[str, ProviderConfig] = {
        cfg.provider: cfg for cfg in result.scalars().all()
    }

    output = []
    for p in static_providers:
        name = p["name"]
        cfg = db_configs.get(name)
        env_key = getattr(settings, f"{name}_api_key", "")
        has_key = bool((cfg and cfg.api_key) or env_key)

        output.append(ProviderOut(
            name=name,
            label=p["label"],
            models=p["models"],
            configured=has_key,
            active=cfg.active if cfg else (name == settings.default_provider),
            active_model=cfg.active_model if cfg else settings.default_model,
        ))

    return output


@router.get("/{provider_name}/key")
async def get_masked_key(
    provider_name: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Return a masked version of the stored API key for the given provider.

    Masking rule: shows first 6 + bullets + last 4 characters for keys longer
    than 12 chars, or first 3 + bullets + last 3 for shorter keys.

    Args:
        provider_name: Internal provider name (e.g. 'gemini', 'openai').
        db:            Injected async database session.

    Returns:
        dict: {'masked_key': 'AIzaSy...abcd'} or {'masked_key': None} if no key is stored.

    Raises:
        HTTPException(404): If the provider name is not recognised.
    """
    known = {p["name"] for p in list_providers()}
    if provider_name not in known:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_name}'.")

    result = await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider == provider_name)
    )
    cfg = result.scalar_one_or_none()

    settings = get_settings()
    raw_key = (cfg.api_key if cfg and cfg.api_key
               else getattr(settings, f"{provider_name}_api_key", "") or "")

    if not raw_key:
        return {"masked_key": None}

    # Mask: show first 6 + ... + last 4 characters
    if len(raw_key) <= 12:
        masked = raw_key[:3] + "\u2022" * (len(raw_key) - 6) + raw_key[-3:]
    else:
        masked = raw_key[:6] + "\u2022\u2022\u2022\u2022\u2022\u2022" + raw_key[-4:]

    return {"masked_key": masked}


@router.put("/{provider_name}", response_model=ProviderOut)
async def update_provider(
    provider_name: str,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create or update a provider's configuration.

    If active=True is set, all other providers are deactivated (single-active
    constraint enforced at service layer). Validates API key format before
    persisting.

    Args:
        provider_name: Internal provider name (e.g. 'gemini', 'openai').
        body:          Fields to update (api_key, active_model, active).
        db:            Injected async database session.

    Returns:
        ProviderOut: The updated provider enriched with static metadata.

    Raises:
        HTTPException(404): If the provider name is not recognised.
        HTTPException(422): If the API key format is invalid.
    """
    known = {p["name"] for p in list_providers()}
    if provider_name not in known:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider_name}'.")

    # Validate API key format if provided
    if body.api_key:
        settings = get_settings()
        try:
            provider_instance = get_provider(
                provider_name,
                api_key=body.api_key,
                model=body.active_model or settings.default_model,
            )
            if not provider_instance.validate_api_key(body.api_key):
                raise HTTPException(
                    status_code=422,
                    detail=f"API key format is invalid for provider '{provider_name}'.",
                )
        except ValueError:
            pass  # Unknown provider already caught above

    # Fetch or create DB record
    result = await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider == provider_name)
    )
    cfg = result.scalar_one_or_none()
    if cfg is None:
        import uuid
        cfg = ProviderConfig(id=str(uuid.uuid4()), provider=provider_name)
        db.add(cfg)

    if body.api_key is not None:
        cfg.api_key = body.api_key
    if body.active_model is not None:
        # Validate: reject [object Object] artifacts and non-string values
        am = body.active_model
        if isinstance(am, str) and "[object" not in am and am.strip():
            cfg.active_model = am.strip()
        else:
            cfg.active_model = None  # let frontend fall back to models[0]
    if body.active is True:
        # Deactivate all other providers
        all_result = await db.execute(select(ProviderConfig))
        for other in all_result.scalars().all():
            if other.provider != provider_name:
                other.active = False
                other.updated_at = datetime.now(timezone.utc)
        cfg.active = True
    elif body.active is False:
        cfg.active = False

    cfg.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Return enriched response
    static = next(p for p in list_providers() if p["name"] == provider_name)
    settings = get_settings()
    env_key = getattr(settings, f"{provider_name}_api_key", "")
    return ProviderOut(
        name=provider_name,
        label=static["label"],
        models=static["models"],
        configured=bool(cfg.api_key or env_key),
        active=cfg.active,
        active_model=cfg.active_model,
    )
