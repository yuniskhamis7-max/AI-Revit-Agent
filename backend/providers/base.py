# -*- coding: utf-8 -*-
"""
Abstract AI Provider — base interface all provider adapters must implement.

The agent service works exclusively against this interface, making it trivial
to add new providers or swap them without touching orchestration logic.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator


# ─────────────────────────────────────────────────────────────────────────────
# Shared System Prompt — used by all providers
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an active AI BIM design assistant operating inside Autodesk Revit. "
    "You have direct access to execute architectural layout modifications using your tools.\n\n"
    "WORKFLOW:\n"
    "1. ANALYZE: Understand the user's request and requirements.\n"
    "2. FETCH: Query the model context using discovery and fetch tools.\n"
    "3. REASON: Formulate placement and configuration logic based on model guidelines and tool instructions.\n"
    "4. EXECUTE: Apply changes to the active document using action tools.\n"
    "5. VERIFY: The last step in the process should be fetching the modified, created, or deleted elements to ensure they were successfully applied.\n\n"
    "CORE PRINCIPLES:\n"
    "- ZERO ASSUMPTIONS: Never invent or guess missing parameter values. Always ask the user for clarification if required inputs are missing.\n"
    "- EFFICIENCY: Avoid redundant data fetching or duplicate operations. Work in feet (convert metric: 1m = 3.28084 ft).\n"
    "- TRANSPARENCY: Report errors, exceptions, or tool limitations clearly to the user without hiding details."
)


class AIProvider(ABC):
    """
    Abstract base class for all AI provider adapters.

    Each concrete adapter (Gemini, OpenAI, Anthropic) wraps its SDK and
    normalises output into a unified stream of event dicts. The agent service
    consumes this stream and translates it into SSE payloads for the frontend.
    """

    # Human-readable name shown in the frontend dropdown
    name: str = ""

    # List of model IDs this provider exposes to the frontend
    available_models: list[str] = []

    @abstractmethod
    async def stream_agent_turn(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        system_prompt: str,
    ) -> AsyncGenerator[dict, None]:
        """
        Runs one agent turn and yields normalised event dicts.

        The caller (agent.py) drives a multi-turn loop by feeding tool results
        back in subsequent calls. Each call represents exactly one model
        inference step.

        Yields dicts with a mandatory 'type' key. Possible types:

          {"type": "text_delta", "content": "<chunk>"}
            Incremental text from the model. May be yielded multiple times.

          {"type": "tool_call", "id": "<str>", "name": "<str>", "args": {}}
            The model wants to call a tool. May be yielded multiple times
            (once per tool call if the model batches several).

          {"type": "done"}
            The model has finished its response for this turn.
            After this event the caller should check for tool_calls and
            decide whether to loop.

        Args:
            messages:     Full conversation history in provider-agnostic format.
                          Each dict has keys: role ('user'|'assistant'|'tool'),
                          content (str), and optionally tool_call_id / name.
            tool_schemas: Raw tool schema dicts from ToolRegistry.schemas.
            system_prompt: The agent's system instruction string.
        """
        ...
        yield  # type: ignore[misc]  # makes this a valid abstract async generator

    @abstractmethod
    def validate_api_key(self, api_key: str) -> bool:
        """
        Perform a lightweight synchronous check that the key is non-empty
        and has the expected format for this provider. Does NOT make a network
        call — that would be too slow for a settings save operation.
        """
        ...
