# -*- coding: utf-8 -*-
"""
OpenAI Provider Adapter.

Wraps the openai SDK via the shared OpenAICompatibleProvider base class.
Supports GPT-4o and o-series models.

The message conversion helpers (_to_openai_messages, _to_openai_tools) live
in openai_compat.py — they are shared with Groq, OpenRouter, and any future
OpenAI-compatible provider. Do NOT duplicate them here.
"""
from __future__ import annotations

import logging

from providers.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o3-mini",
    "gpt-4-turbo",
]
"""Static list of OpenAI model IDs surfaced in the frontend dropdown."""


class OpenAIProvider(OpenAICompatibleProvider):
    """
    OpenAI provider adapter.

    Uses the standard api.openai.com endpoint for GPT-4o and o-series models.
    Inherits stream_agent_turn, validate_api_key, and all message/tool
    conversion logic from OpenAICompatibleProvider.

    Attributes:
        name:             Provider identifier ('openai').
        base_url:         OpenAI API endpoint.
        default_model:    Default model when none is specified.
        available_models: List of model IDs surfaced in the frontend.
    """
    name = "openai"
    base_url = "https://api.openai.com/v1"
    default_model = "gpt-4o"
    available_models = OPENAI_MODELS

    def validate_api_key(self, api_key: str) -> bool:
        """
        Check that the API key has the expected OpenAI prefix.

        Args:
            api_key: Key to validate.

        Returns:
            bool: True if the key is non-empty and starts with 'sk-'.
        """
        return bool(api_key and api_key.startswith("sk-"))
