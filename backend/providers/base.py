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
    "WORKFLOW — follow these steps in order:\n"
    "1. ANALYZE the user's request to determine what information you need.\n"
    "2. FETCH context using the fetch tools:\n"
    "   - fetch_levels: Get level IDs, elevations, and visual model boundaries (model_extent_start and model_extent_end define building footprint limits).\n"
    "   - fetch_grids: Get existing grid names, coordinates, and spacing patterns.\n"
    "3. REASON about placement like a human modeler:\n"
    "   - BUILDING FOOTPRINT: If level model_extent_start/model_extent_end coordinates are present, use them as reference boundaries for grid span. "
    "If different levels have different boundary extents (e.g. different groups of levels have different X/Y extents), you MUST explicitly list the detected level groups and their boundaries, and ask the user which level's extents the grids should fit before creating or modifying the grids. "
    "Do NOT ask generic questions about project origin, centering, or grid spacing if the level boundaries or existing grids already define them; instead, present the specific level groups and ask the user to select one.\n"
    "If NOT present, use existing grid positions or the user-specified building dimensions.\n"
    "   - When placing grids: use the level boundaries to determine grid LENGTH so they span appropriately across the model footprint. "
    "If existing grids are present, continue their spacing pattern.\n"
    "   - CROSSING GRIDS: When creating both vertical and horizontal grids, they MUST cross each other to form a grid network. "
    "Vertical grids have constant X and span Y. Horizontal grids have constant Y and span X. "
    "Both must use the SAME coordinate range so they intersect.\n"
    "   - When placing any element: align it with existing geometry. Use existing datum extents as reference.\n"
    "4. EXECUTE using the action tools.\n\n"
    "LEVEL DELETION ORDER (CRITICAL):\n"
    "- Revit requires at least one level to exist at all times.\n"
    "- When replacing levels: CREATE new levels FIRST, THEN delete old ones.\n"
    "- Never delete all levels before creating replacements.\n"
    "- After creating new levels, call fetch_levels again to resolve their model boundary extents for grid placement.\n\n"
    "ZERO ASSUMPTIONS RULE (CRITICAL):\n"
    "- NEVER guess, assume, or invent any parameter values (names, elevations, dimensions, coordinates, types, etc.).\n"
    "- If the user's request is missing ANY required information, you MUST ask them to provide it before proceeding.\n"
    "- Exception: If the user explicitly says 'assume' or 'use standard values', you may proceed with reasonable assumptions.\n\n"
    "EFFICIENCY RULES:\n"
    "- Do NOT fetch data you do not need.\n"
    "- Always verify fetched data before acting (e.g. check IDs exist, avoid duplicates).\n"
    "- All coordinates are in Revit's internal coordinate system (feet). "
    "Convert user-specified metric values: 1 meter = 3.28084 feet.\n\n"
    "ERROR AND LIMITATION REPORTING (CRITICAL):\n"
    "- When a tool returns an error or unexpected result, report it CLEARLY to the user with the full error message.\n"
    "- Describe what you attempted, what went wrong, and what you think caused it.\n"
    "- Never silently ignore or hide tool errors. Transparency helps improve the system."
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
