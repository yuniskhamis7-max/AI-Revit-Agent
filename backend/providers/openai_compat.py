# -*- coding: utf-8 -*-
"""
OpenAI-Compatible Provider Base — shared adapter for providers that expose
an OpenAI-compatible chat completions endpoint (Groq, OpenRouter, etc.).

Subclasses only need to set class-level constants (name, base_url, models).
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from providers.base import AIProvider, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(AIProvider):
    """Base class for OpenAI-compatible providers (different base_url)."""

    # Override in subclasses
    base_url: str = "https://api.openai.com/v1"
    default_model: str = ""
    # Set to a positive int to truncate tool descriptions (helps models that struggle with complex schemas)
    max_tool_description_length: int | None = None

    def __init__(self, api_key: str, model: str | None = None) -> None:
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=api_key, base_url=self.base_url)
        except ImportError:
            self._client = None
            logger.warning("openai package not installed. %s provider unavailable.", self.name)
        # Ensure model is a valid string — reject objects / [object Object] artifacts
        m = model or self.default_model or (self.available_models[0] if self.available_models else "")
        if not isinstance(m, str) or "[object" in m or not m.strip():
            m = self.default_model or (self.available_models[0] if self.available_models else "")
        self._model = m.strip()

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and len(api_key) > 8)

    async def stream_agent_turn(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        system_prompt: str,
    ) -> AsyncGenerator[dict, None]:
        if self._client is None:
            yield {"type": "error", "content": f"openai package not installed ({self.name})."}
            yield {"type": "done"}
            return

        oai_messages = _to_openai_messages(messages, system_prompt)
        oai_tools = _to_openai_tools(tool_schemas, max_desc_length=self.max_tool_description_length)

        kwargs: dict = {
            "model": self._model,
            "messages": oai_messages,
            "temperature": 0,
            "stream": True,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        tool_call_accumulators: dict[int, dict] = {}

        try:
            async with await self._client.chat.completions.create(**kwargs) as stream:
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta is None:
                        continue

                    if delta.content:
                        yield {"type": "text_delta", "content": delta.content}

                    for tc in (delta.tool_calls or []):
                        idx = tc.index
                        if idx not in tool_call_accumulators:
                            tool_call_accumulators[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name if tc.function else "",
                                "args_str": "",
                            }
                        if tc.function:
                            if tc.function.name:
                                tool_call_accumulators[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_call_accumulators[idx]["args_str"] += tc.function.arguments

        except Exception as exc:
            logger.error("Stream error from %s: %s", self.name, exc)
            yield {"type": "error", "content": f"{self.name} API error: {exc}"}

        for acc in tool_call_accumulators.values():
            try:
                args = json.loads(acc["args_str"]) if acc["args_str"] else {}
            except json.JSONDecodeError:
                args = {}
            yield {
                "type": "tool_call",
                "id": acc["id"],
                "name": acc["name"],
                "args": args,
            }

        yield {"type": "done"}


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers (same as openai.py)
# ─────────────────────────────────────────────────────────────────────────────

def _to_openai_messages(messages: list[dict], system_prompt: str) -> list[dict]:
    """Convert provider-agnostic messages to OpenAI chat format."""
    result: list[dict] = []
    result.append({"role": "system", "content": system_prompt or SYSTEM_PROMPT})
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "user":
            result.append({"role": "user", "content": content})

        elif role == "assistant":
            oai_msg: dict = {"role": "assistant", "content": content or None}
            tcs = msg.get("tool_calls", [])
            if tcs:
                oai_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])},
                    }
                    for tc in tcs
                ]
            result.append(oai_msg)

        elif role == "tool":
            result.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": content,
            })

    return result


def _to_openai_tools(tool_schemas: list[dict], max_desc_length: int | None = None) -> list[dict]:
    """Convert raw bridge schemas to OpenAI tool format.

    Args:
        tool_schemas: Raw tool definitions from the bridge.
        max_desc_length: If set, truncate the combined description to this many characters.
                         Useful for models that struggle with complex tool schemas (e.g. Groq).
    """
    result = []
    for s in tool_schemas:
        description = s["description"]
        agent_instructions = s.get("agent_instructions", "")
        if agent_instructions:
            description = description + "\n\nBEFORE CALLING: " + agent_instructions
        if max_desc_length and len(description) > max_desc_length:
            description = description[:max_desc_length - 3] + "..."
        result.append({
            "type": "function",
            "function": {
                "name": s["name"],
                "description": description,
                "parameters": s.get("parameters", {}),
            },
        })
    return result
