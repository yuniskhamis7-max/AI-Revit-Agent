# -*- coding: utf-8 -*-
"""
Provider Factory — resolves provider name → AIProvider instance.

Extensible adapter pattern allowing new models to be added by implementing
the AIProvider interface and registering them here.
"""
from __future__ import annotations

from providers.base import AIProvider

def get_provider(provider_name: str, api_key: str, model: str) -> AIProvider:
    """
    Instantiate and return an AIProvider for the given provider name.
    """
    match provider_name.lower():
        case "gemini":
            from providers.gemini import GeminiProvider
            return GeminiProvider(api_key=api_key, model=model)
        case _:
            raise ValueError(
                f"Unknown provider '{provider_name}'. Currently supported active: gemini. "
                "To add more, implement the AIProvider adapter in backend/providers."
            )

def list_providers() -> list[dict]:
    """
    Returns metadata for all supported providers.
    """
    from providers.gemini import GEMINI_MODELS
    return [
        {"name": "gemini", "label": "Google Gemini", "models": GEMINI_MODELS},
    ]

def list_providers_with_dynamic_models(api_key: str | None = None) -> list[dict]:
    """
    Returns metadata for all supported providers with dynamically fetched models.
    """
    if api_key:
        from providers.gemini import fetch_gemini_models
        gemini_models = fetch_gemini_models(api_key)
    else:
        from providers.gemini import GEMINI_MODELS
        gemini_models = list(GEMINI_MODELS)

    return [
        {"name": "gemini", "label": "Google Gemini", "models": gemini_models},
    ]
