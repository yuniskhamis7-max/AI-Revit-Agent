# -*- coding: utf-8 -*-
"""
OpenAI Provider Adapter.

Wraps the openai SDK and normalises its streaming response into the
provider-agnostic event format. Supports GPT-4o and o-series models.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from providers.base import AIProvider, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "o3-mini",
    "gpt-4-turbo",
]


class OpenAIProvider(AIProvider):
    name = "openai"
    available_models = OPENAI_MODELS

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        # Lazy import so missing package doesn't crash the whole backend
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=api_key)
        except ImportError:
            self._client = None
            logger.warning("openai package not installed. OpenAI provider unavailable.")
        self._model = model

    def validate_api_key(self, api_key: str) -> bool:
        return bool(api_key and api_key.startswith("sk-"))

    async def stream_agent_turn(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        system_prompt: str,
    ) -> AsyncGenerator[dict, None]:
        if self._client is None:
            yield {"type": "error", "content": "openai package not installed."}
            yield {"type": "done"}
            return

        oai_messages = _to_openai_messages(messages, system_prompt)
        oai_tools = _to_openai_tools(tool_schemas)

        kwargs = {
            "model": self._model,
            "messages": oai_messages,
            "temperature": 0,
            "stream": True,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        tool_call_accumulators: dict[int, dict] = {}
        full_text = ""

        async with await self._client.chat.completions.create(**kwargs) as stream:  # type: ignore[attr-defined]
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta is None:
                    continue

                # Text chunk
                if delta.content:
                    full_text += delta.content
                    yield {"type": "text_delta", "content": delta.content}

                # Tool call chunks (streamed incrementally by OpenAI)
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

        # Emit completed tool calls after streaming finishes
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


def _to_openai_messages(messages: list[dict], system_prompt: str) -> list[dict]:
    """Convert provider-agnostic messages to OpenAI chat format."""
    result = [{"role": "system", "content": system_prompt or SYSTEM_PROMPT}]
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


def _to_openai_tools(tool_schemas: list[dict]) -> list[dict]:
    """Convert raw bridge schemas to OpenAI tool format."""
    result = []
    for s in tool_schemas:
        description = s["description"]
        agent_instructions = s.get("agent_instructions", "")
        if agent_instructions:
            description = description + "\n\nBEFORE CALLING: " + agent_instructions
        result.append({
            "type": "function",
            "function": {
                "name": s["name"],
                "description": description,
                "parameters": s.get("parameters", {}),
            },
        })
    return result
