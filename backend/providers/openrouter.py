# -*- coding: utf-8 -*-
"""
OpenRouter Provider Adapter — meta-provider that routes to many LLM providers.

OpenRouter gives access to models from OpenAI, Anthropic, Google, Meta, Mistral,
and many others through a single OpenAI-compatible API.
Base URL: https://openrouter.ai/api/v1
Key format: sk-or-...
"""
from __future__ import annotations

from providers.openai_compat import OpenAICompatibleProvider

OPENROUTER_MODELS = [
    "anthropic/claude-sonnet-4",
    "google/gemini-2.5-flash",
    "openai/gpt-4o",
    "meta-llama/llama-4-maverick",
    "deepseek/deepseek-r1",
    "mistralai/mistral-large",
    "qwen/qwen3-235b-a22b",
]


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    available_models = OPENROUTER_MODELS
    base_url = "https://openrouter.ai/api/v1"
    default_model = "anthropic/claude-sonnet-4"

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("sk-or-"))
