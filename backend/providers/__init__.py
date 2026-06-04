# -*- coding: utf-8 -*-
"""
Provider Factory — resolves provider name → AIProvider instance.

All provider instantiation goes through here. The agent service and API routes
never import provider classes directly, keeping the coupling one level removed.
"""
from __future__ import annotations

from providers.base import AIProvider


def get_provider(provider_name: str, api_key: str, model: str) -> AIProvider:
    """
    Instantiate and return an AIProvider for the given provider name.

    Raises ValueError for unknown provider names — callers should catch this
    and return a 400 to the frontend.
    """
    match provider_name.lower():
        case "gemini":
            from providers.gemini import GeminiProvider
            return GeminiProvider(api_key=api_key, model=model)
        case "openai":
            from providers.openai import OpenAIProvider
            return OpenAIProvider(api_key=api_key, model=model)
        case "anthropic":
            from providers.anthropic import AnthropicProvider
            return AnthropicProvider(api_key=api_key, model=model)
        case "groq":
            from providers.groq import GroqProvider
            return GroqProvider(api_key=api_key, model=model)
        case "openrouter":
            from providers.openrouter import OpenRouterProvider
            return OpenRouterProvider(api_key=api_key, model=model)
        case _:
            raise ValueError(f"Unknown provider '{provider_name}'. Supported: gemini, openai, anthropic, groq, openrouter")


def list_providers() -> list[dict]:
    """
    Returns metadata for all supported providers (used by GET /api/providers).
    Importing model lists here avoids importing the full SDK modules.
    """
    from providers.gemini import GEMINI_MODELS
    from providers.openai import OPENAI_MODELS
    from providers.anthropic import ANTHROPIC_MODELS
    from providers.groq import GROQ_MODELS
    from providers.openrouter import OPENROUTER_MODELS

    return [
        {"name": "gemini",     "label": "Google Gemini",    "models": GEMINI_MODELS},
        {"name": "openai",     "label": "OpenAI",           "models": OPENAI_MODELS},
        {"name": "anthropic",  "label": "Anthropic Claude", "models": ANTHROPIC_MODELS},
        {"name": "groq",       "label": "Groq (LPU)",       "models": GROQ_MODELS},
        {"name": "openrouter", "label": "OpenRouter",       "models": OPENROUTER_MODELS},
    ]


def list_providers_with_dynamic_models(api_key: str | None = None) -> list[dict]:
    """
    Returns metadata for all supported providers with dynamically fetched models
    for Gemini (when an API key is available). Other providers use static lists.
    """
    from providers.openai import OPENAI_MODELS
    from providers.anthropic import ANTHROPIC_MODELS
    from providers.groq import GROQ_MODELS
    from providers.openrouter import OPENROUTER_MODELS

    # Fetch Gemini models dynamically if API key provided
    if api_key:
        from providers.gemini import fetch_gemini_models
        gemini_models = fetch_gemini_models(api_key)
    else:
        from providers.gemini import GEMINI_MODELS
        gemini_models = list(GEMINI_MODELS)

    return [
        {"name": "gemini",     "label": "Google Gemini",    "models": gemini_models},
        {"name": "openai",     "label": "OpenAI",           "models": OPENAI_MODELS},
        {"name": "anthropic",  "label": "Anthropic Claude", "models": ANTHROPIC_MODELS},
        {"name": "groq",       "label": "Groq (LPU)",       "models": GROQ_MODELS},
        {"name": "openrouter", "label": "OpenRouter",       "models": OPENROUTER_MODELS},
    ]
