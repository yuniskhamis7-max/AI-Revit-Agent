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


class GroqProvider(OpenAICompatibleProvider):
    name = "groq"
    available_models = GROQ_MODELS
    base_url = "https://api.groq.com/openai/v1"
    default_model = "llama-3.3-70b-versatile"
    # Groq models can struggle with very long tool descriptions (e.g. create_grid
    # has 1500+ char agent_instructions). Truncate to keep the core description
    # while reducing overall schema complexity.
    max_tool_description_length = 400

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("gsk_"))
