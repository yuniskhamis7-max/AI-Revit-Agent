# -*- coding: utf-8 -*-
"""
Specialised BIM Agent Definitions.

All agent system prompts are stored externally under backend/core/prompts/
and loaded dynamically on instantiation to keep Python code clean and maintainable.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import AsyncGenerator

from providers.base import AIProvider

logger = logging.getLogger(__name__)

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


def load_prompt(filename: str) -> str:
    """Load prompt string from the prompts folder."""
    path = os.path.join(PROMPTS_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as exc:
        logger.error("Failed to load prompt template from %s: %s", path, exc)
        raise RuntimeError(f"Prompt template missing: {filename}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# Base Agent
# ─────────────────────────────────────────────────────────────────────────────

class BaseAgent:
    """
    Common base for all BIM agents.

    Provides:
      • generate_response() — blocking accumulation of one LLM turn.
      • stream_turn()       — async generator of raw provider events.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        self.provider = provider
        self.tool_schemas = tool_schemas or []

    async def generate_response(
        self,
        messages: list[dict],
        system_prompt: str,
        tool_schemas: list[dict] | None = None,
    ) -> str:
        """
        Run a single LLM inference turn and return the full accumulated text.
        Raises RuntimeError on provider error so callers can catch cleanly.
        """
        text_parts: list[str] = []
        try:
            async for event in self.provider.stream_agent_turn(
                messages=messages,
                tool_schemas=tool_schemas or [],
                system_prompt=system_prompt,
            ):
                if event.get("type") == "text_delta":
                    text_parts.append(event["content"])
                elif event.get("type") == "error":
                    raise RuntimeError(event.get("content", "Provider returned an error"))
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception("BaseAgent.generate_response() raised unexpectedly")
            raise RuntimeError(f"Agent inference failed: {exc}") from exc

        return "".join(text_parts)

    async def stream_turn(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
        system_prompt: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Yield raw provider events for a tool-calling turn.
        """
        sp = system_prompt or getattr(self, "SYSTEM_PROMPT", "")
        async for event in self.provider.stream_agent_turn(
            messages=messages,
            tool_schemas=tool_schemas,
            system_prompt=sp,
        ):
            yield event


# ─────────────────────────────────────────────────────────────────────────────
# Task Classifier Agent
# ─────────────────────────────────────────────────────────────────────────────

class TaskClassifier(BaseAgent):
    """
    Classifies the user's request as SIMPLE or COMPLEX.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        super().__init__(provider, tool_schemas)
        self.SYSTEM_PROMPT = load_prompt("task_classifier.txt")

    async def classify(self, history: list[dict]) -> str:
        """Return 'SIMPLE' or 'COMPLEX'."""
        result = await self.generate_response(history, self.SYSTEM_PROMPT)
        return "COMPLEX" if "COMPLEX" in result.strip().upper() else "SIMPLE"


# ─────────────────────────────────────────────────────────────────────────────
# Agent 1 — BIM Intent Clarifier
# ─────────────────────────────────────────────────────────────────────────────

class BIMIntentClarifierAgent(BaseAgent):
    """
    Agent 1 — Design Intent Clarifier.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        super().__init__(provider, tool_schemas)
        self.SYSTEM_PROMPT = load_prompt("intent_clarifier.txt")

    async def clarify(self, history: list[dict]) -> str:
        """Run one clarification turn. Returns the agent's full text response."""
        return await self.generate_response(history, self.SYSTEM_PROMPT)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 2 — BIM Design Manual Generator
# ─────────────────────────────────────────────────────────────────────────────

class BIMDesignManualAgent(BaseAgent):
    """
    Agent 2 — Input Design Manual Generator.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        super().__init__(provider, tool_schemas)
        self.SYSTEM_PROMPT = load_prompt("design_manual.txt")

    async def generate_manual(
        self,
        intent_text: str,
        existing_state_summary: str = "",
    ) -> str:
        """
        Generate the Input Design Manual from the confirmed design intent.
        """
        prompt = (
            "Generate the Input Design Manual for this confirmed design intent:\n\n"
            f"{intent_text}"
        )
        if existing_state_summary:
            prompt += (
                "\n\n---\n"
                "EXISTING REVIT PROJECT STATE\n"
                "(For reference — mark elements as PRE-EXISTING where applicable):\n\n"
                f"{existing_state_summary}"
            )
        if self.tool_schemas:
            clean_schemas = [{"name": s["name"], "description": s.get("description", ""), "parameters": s.get("parameters", {})} for s in self.tool_schemas]
            prompt += (
                "\n\n---\n"
                "ACTIVE REVIT TOOLS SCHEMAS:\n"
                "Compile design manual tables mapping directly to these parameters:\n\n"
                f"```json\n{json.dumps(clean_schemas, indent=2)}\n```"
            )
        messages = [{"role": "user", "content": prompt}]
        return await self.generate_response(messages, self.SYSTEM_PROMPT)


# ─────────────────────────────────────────────────────────────────────────────
# Agent 3 — BIM Execution Planner
# ─────────────────────────────────────────────────────────────────────────────

class BIMExecutionPlannerAgent(BaseAgent):
    """
    Agent 3 — Execution Planner.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        super().__init__(provider, tool_schemas)
        self.SYSTEM_PROMPT = load_prompt("execution_planner.txt")

    async def create_plan(
        self,
        design_manual: str,
        existing_state_summary: str = "",
    ) -> str:
        """
        Create an execution strategy plan from the Input Design Manual.
        """
        prompt = (
            "Create an Execution Plan for the following Input Design Manual:\n\n"
            f"{design_manual}"
        )
        if existing_state_summary:
            prompt += (
                "\n\n---\n"
                "EXISTING REVIT STATE:\n\n"
                f"{existing_state_summary}"
            )
        if self.tool_schemas:
            clean_schemas = [{"name": s["name"], "description": s.get("description", ""), "parameters": s.get("parameters", {})} for s in self.tool_schemas]
            prompt += (
                "\n\n---\n"
                "ACTIVE REVIT TOOLS SCHEMAS:\n"
                "Plan dependency ordering and validation checklist mapping to these tools:\n\n"
                f"```json\n{json.dumps(clean_schemas, indent=2)}\n```"
            )
        messages = [{"role": "user", "content": prompt}]
        return await self.generate_response(messages, self.SYSTEM_PROMPT)


# ─────────────────────────────────────────────────────────────────────────────
# Helper — BIM Parser Agent (Bidirectional)
# ─────────────────────────────────────────────────────────────────────────────

class BIMParserAgent(BaseAgent):
    """
    Helper — Bidirectional Parser.

    Forward mode  (Phase 4): Design Manual → execute_batch JSON (one-shot LLM call).
    Reverse mode  (Phase 6): execute_batch result → fetch real Revit state → Result DM.
                             Runs as a tool-calling agent loop so it can autonomously
                             decide which fetch_* tools to call based on what was created,
                             regardless of the element categories involved.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        super().__init__(provider, tool_schemas)
        self._FORWARD_SYSTEM_PROMPT = load_prompt("parser_forward.txt")
        self._REVERSE_SYSTEM_PROMPT = load_prompt("parser_reverse.txt")

    # ── Phase 4: Forward parse ────────────────────────────────────────────────

    async def manual_to_json(
        self,
        design_manual: str,
        existing_state_summary: str = "",
        execution_plan: str = "",
    ) -> str:
        """
        Convert the Input Design Manual to an execute_batch JSON payload string.
        """
        prompt = (
            "Convert this Input Design Manual to an execute_batch JSON payload:\n\n"
            f"{design_manual}"
        )
        if existing_state_summary:
            prompt += (
                "\n\n---\n"
                "EXISTING REVIT STATE\n"
                "(OMIT create_* calls for PRE-EXISTING elements):\n\n"
                f"{existing_state_summary}"
            )
        if execution_plan:
            prompt += (
                "\n\n---\n"
                "EXECUTION PLAN (follow its constraints and ordering):\n\n"
                f"{execution_plan}"
            )
        if self.tool_schemas:
            clean_schemas = [
                {"name": s["name"], "description": s.get("description", ""),
                 "parameters": s.get("parameters", {})}
                for s in self.tool_schemas
            ]
            prompt += (
                "\n\n---\n"
                "ACTIVE REVIT TOOLS SCHEMAS:\n"
                "Construct tool-call JSON arguments mapping to these schemas:\n\n"
                f"```json\n{json.dumps(clean_schemas, indent=2)}\n```"
            )

        messages = [{"role": "user", "content": prompt}]
        raw = await self.generate_response(messages, self._FORWARD_SYSTEM_PROMPT)

        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        return match.group(1).strip() if match else raw.strip()

    # ── Phase 6: Reverse parse (tool-calling agent loop) ─────────────────────

    def build_reverse_messages(
        self,
        batch_result: dict,
        input_design_manual: str = "",
    ) -> list[dict]:
        """
        Build the initial message list to kick off the reverse-parse agent loop.

        The parser agent will analyse the batch result, infer which fetch_* tools
        correspond to the categories that were created, call those tools, and emit
        a Result Design Manual with real Revit values as its final text.

        The caller (orchestrator) drives the actual AgentOrchestrator loop so that
        tool calls from the parser are executed and results fed back automatically.
        This pattern is fully generic: adding any new create_X / fetch_Xs tool pair
        requires zero changes here — the LLM infers the mapping at runtime.
        """
        batch_result_json = json.dumps(batch_result, indent=2)

        content = (
            "Here is the execute_batch result from a Revit operation:\n\n"
            f"```json\n{batch_result_json}\n```\n\n"
            "Analyse this result, call the appropriate fetch_* tools to retrieve the "
            "actual Revit state for every element that was created, and produce the "
            "Result Design Manual."
        )

        if input_design_manual:
            content += (
                "\n\n---\n"
                "REFERENCE — Input Design Manual (use ONLY for table structure alignment, "
                "NOT as a source of parameter values):\n\n"
                f"{input_design_manual}"
            )

        # Expose only the fetch_* subset of schemas — built dynamically from
        # whatever tools are registered at runtime.  No hardcoding required.
        fetch_schemas = [
            s for s in (self.tool_schemas or [])
            if s.get("name", "").startswith("fetch_")
        ]
        if fetch_schemas:
            clean_fetch = [
                {"name": s["name"], "description": s.get("description", ""),
                 "parameters": s.get("parameters", {})}
                for s in fetch_schemas
            ]
            content += (
                "\n\n---\n"
                "AVAILABLE FETCH TOOLS (call these to retrieve actual Revit data):\n\n"
                f"```json\n{json.dumps(clean_fetch, indent=2)}\n```"
            )

        return [{"role": "user", "content": content}]

    @property
    def reverse_system_prompt(self) -> str:
        """Expose the reverse-parse system prompt for the orchestrator's AgentOrchestrator."""
        return self._REVERSE_SYSTEM_PROMPT


# ─────────────────────────────────────────────────────────────────────────────
# Agent 5 — BIM Validator
# ─────────────────────────────────────────────────────────────────────────────

class BIMValidatorAgent(BaseAgent):
    """
    Agent 5 — BIM Validator.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        super().__init__(provider, tool_schemas)
        self.SYSTEM_PROMPT = load_prompt("validator.txt")

    async def validate(self, input_manual: str, result_manual: str) -> str:
        """
        Validate result against intent and return the full validation report text.
        """
        payload = (
            "INPUT DESIGN MANUAL (expected — what was intended):\n\n"
            f"{input_manual}\n\n"
            "---\n\n"
            "RESULT DESIGN MANUAL (actual — what Revit created):\n\n"
            f"{result_manual}"
        )
        if self.tool_schemas:
            clean_schemas = [{"name": s["name"], "description": s.get("description", ""), "parameters": s.get("parameters", {})} for s in self.tool_schemas]
            payload += (
                "\n\n---\n"
                "ACTIVE REVIT TOOLS SCHEMAS:\n"
                "Use these schemas to verify expected parameter names and units:\n\n"
                f"```json\n{json.dumps(clean_schemas, indent=2)}\n```"
            )
        messages = [{"role": "user", "content": payload}]
        return await self.generate_response(messages, self.SYSTEM_PROMPT)


# ─────────────────────────────────────────────────────────────────────────────
# Simple Task Agent
# ─────────────────────────────────────────────────────────────────────────────

class SimpleTaskAgent(BaseAgent):
    """
    Simple Task Agent — handles direct Revit queries and single-element operations.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict] | None = None) -> None:
        super().__init__(provider, tool_schemas)
        self.SYSTEM_PROMPT = load_prompt("simple_task.txt")

    async def stream_turn(
        self,
        messages: list[dict],
        tool_schemas: list[dict],
    ) -> AsyncGenerator[dict, None]:
        """Yield provider events for a tool-calling turn."""
        async for event in self.provider.stream_agent_turn(
            messages=messages,
            tool_schemas=tool_schemas,
            system_prompt=self.SYSTEM_PROMPT,
        ):
            yield event
