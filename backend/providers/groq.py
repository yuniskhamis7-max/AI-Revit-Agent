# -*- coding: utf-8 -*-
"""
Groq Provider Adapter — uses Groq's OpenAI-compatible API for fast inference.

Groq provides ultra-fast inference via LPU (Language Processing Unit) hardware.
Base URL: https://api.groq.com/openai/v1
Key format: gsk_...
"""
from __future__ import annotations

from providers.openai_compat import OpenAICompatibleProvider

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
]
"""Static list of Groq model IDs surfaced in the frontend dropdown."""


class GroqProvider(OpenAICompatibleProvider):
    """
    Groq provider adapter — uses Groq's OpenAI-compatible API for ultra-fast inference.

    Groq provides inference via LPU (Language Processing Unit) hardware at
    very high token throughput. Uses the shared OpenAI-compatible base class
    with a custom base_url and truncated tool descriptions (Groq's Llama
    models can struggle with very long tool schemas).

    Attributes:
        name:                       Provider identifier ('groq').
        available_models:           List of Groq-hosted model IDs.
        base_url:                   Groq's OpenAI-compatible API endpoint.
        default_model:              Default model when none is specified.
        max_tool_description_length: Truncation limit for tool descriptions (400 chars).
    """
    name = "groq"
    available_models = GROQ_MODELS
    base_url = "https://api.groq.com/openai/v1"
    default_model = "llama-3.3-70b-versatile"
    # Groq models can struggle with very long tool descriptions (e.g. create_grid
    # has 1500+ char agent_instructions). Truncate to keep the core description
    # while reducing overall schema complexity.
    max_tool_description_length = 400

    def validate_api_key(self, api_key: str) -> bool:
        """
        Check that the API key has the expected Groq prefix.

        Args:
            api_key: Key to validate.

        Returns:
            bool: True if the key is non-empty and starts with 'gsk_'.
        """
        return bool(api_key and api_key.startswith("gsk_"))
