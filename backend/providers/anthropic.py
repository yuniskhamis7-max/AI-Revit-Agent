# -*- coding: utf-8 -*-
"""
Anthropic Provider Adapter.

Wraps the anthropic SDK and normalises its streaming response into the
provider-agnostic event format. Supports Claude 3.x models.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from providers.base import AIProvider, SYSTEM_PROMPT

logger = logging.getLogger(__name__)

ANTHROPIC_MODELS = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-3-5",
    "claude-3-5-sonnet-latest",
]
"""Static list of Anthropic model IDs surfaced in the frontend dropdown."""


class AnthropicProvider(AIProvider):
    """
    Anthropic Claude provider adapter.

    Wraps the anthropic SDK and normalises its streaming response into the
    provider-agnostic event format consumed by the agent service. Tool calls
    are collected after the stream completes (not streamed incrementally).

    Attributes:
        name:             Provider identifier ('anthropic').
        available_models: List of Claude model IDs available for selection.
    """
    name = "anthropic"
    available_models = ANTHROPIC_MODELS

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5") -> None:
        """
        Initialise the Anthropic provider with an API key and model.

        Args:
            api_key: Anthropic API key (starts with 'sk-ant-').
            model:   Model ID to use. Defaults to 'claude-sonnet-4-5'.
        """
        try:
            import anthropic
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            """Internal async Anthropic client, or None if SDK is not installed."""
        except ImportError:
            self._client = None
            logger.warning("anthropic package not installed. Anthropic provider unavailable.")
        self._model = model
        """Active model ID for this provider instance."""

    def validate_api_key(self, api_key: str) -> bool:
        """
        Check that the API key has the expected Anthropic prefix.

        Args:
            api_key: Key to validate.

        Returns:
            bool: True if the key is non-empty and starts with 'sk-ant-'.
        """
        return bool(api_key and api_key.startswith("sk-ant-"))

    async def stream_agent_turn(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        system_prompt: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Run one Anthropic model inference turn and yield normalised events.

        Converts messages and tools to Anthropic format, streams text deltas,
        then collects the final message for tool use extraction. Tool calls
        are yielded after the stream ends.

        Args:
            messages:      Provider-agnostic conversation history.
            tool_schemas:  Raw tool definitions from the bridge.
            system_prompt: System instruction for the model.

        Yields:
            dict: Normalised events — text_delta, tool_call, error, or done.
        """
        if self._client is None:
            yield {"type": "error", "content": "anthropic package not installed."}
            yield {"type": "done"}
            return

        ant_messages = _to_anthropic_messages(messages)
        ant_tools = _to_anthropic_tools(tool_schemas)

        kwargs = {
            "model": self._model,
            "max_tokens": 8096,
            "system": system_prompt or SYSTEM_PROMPT,
            "messages": ant_messages,
        }
        if ant_tools:
            kwargs["tools"] = ant_tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                event_type = getattr(event, "type", None)

                if event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", None) == "text_delta":
                        yield {"type": "text_delta", "content": delta.text}

                elif event_type == "content_block_stop":
                    # Tool use blocks are complete at this point
                    pass

            # Collect final message for tool use extraction
            final_msg = await stream.get_final_message()

        for block in (final_msg.content or []):
            if getattr(block, "type", None) == "tool_use":
                yield {
                    "type": "tool_call",
                    "id": block.id,
                    "name": block.name,
                    "args": block.input or {},
                }

        yield {"type": "done"}


def _to_anthropic_messages(messages: list[dict]) -> list[dict]:
    """
    Convert provider-agnostic messages to Anthropic Messages API format.

    Anthropic uses a content-block structure for assistant messages (text + tool_use)
    and maps tool results as user messages with tool_result content blocks.

    Args:
        messages: List of dicts with keys: role, content, and optionally tool_calls / tool_call_id.

    Returns:
        list[dict]: Anthropic-native message dicts ready for the Messages API.
    """
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg.get("content", "")

        if role == "user":
            result.append({"role": "user", "content": content})

        elif role == "assistant":
            parts = []
            if content:
                parts.append({"type": "text", "text": content})
            for tc in msg.get("tool_calls", []):
                parts.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["args"],
                })
            result.append({"role": "assistant", "content": parts})

        elif role == "tool":
            result.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id", ""),
                    "content": content,
                }],
            })

    return result


def _to_anthropic_tools(tool_schemas: list[dict]) -> list[dict]:
    """
    Convert raw bridge tool schemas to Anthropic tool format.

    Anthropic uses 'input_schema' instead of 'parameters', and the tool name
    must be unique. If agent_instructions are present, they are appended to
    the description as a BEFORE CALLING note.

    Args:
        tool_schemas: Raw tool definition dicts from the Revit bridge.

    Returns:
        list[dict]: Anthropic-native tool dicts with name, description, input_schema.
    """
    result = []
    for s in tool_schemas:
        description = s["description"]
        agent_instructions = s.get("agent_instructions", "")
        if agent_instructions:
            description = description + "\n\nBEFORE CALLING: " + agent_instructions
        result.append({
            "name": s["name"],
            "description": description,
            "input_schema": s.get("parameters", {"type": "object", "properties": {}}),
        })
    return result
