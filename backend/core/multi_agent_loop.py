# -*- coding: utf-8 -*-
"""
Multi-Agent BIM Orchestration Loop.

Orchestrates routing between simple and complex workflows, driving each phase and
streaming SSE events to the user interface.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, AsyncGenerator, Callable

from providers.base import AIProvider
from core.agent_loop import AgentOrchestrator
from core.agents import (
    BIMIntentClarifierAgent,
    BIMDesignManualAgent,
    BIMExecutionPlannerAgent,
    BIMParserAgent,
    BIMValidatorAgent,
    SimpleTaskAgent,
    TaskClassifier,
)
from core.helpers import (
    fetch_existing_state,
    format_state_summary,
    inject_state_context,
    filter_duplicate_calls,
    inject_schemas_context,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# BIM Orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class BIMOrchestrator:
    """
    Main multi-agent orchestrator.

    Responsibilities:
      1. Classify the task (SIMPLE / COMPLEX).
      2. Route to the appropriate workflow.
      3. Drive each pipeline phase, yielding SSE events at every step so the
         user has a live view of the entire process.
      4. Act as the safety net — the programmatic dedup filter is always applied
         regardless of what the LLM agents emit.
    """

    def __init__(self, provider: AIProvider, tool_schemas: list[dict]) -> None:
        self.provider = provider
        self.tool_schemas = tool_schemas

        # Instantiate all pipeline agents
        self.classifier      = TaskClassifier(provider, tool_schemas)
        self.intent_clarifier = BIMIntentClarifierAgent(provider, tool_schemas)
        self.manual_agent    = BIMDesignManualAgent(provider, tool_schemas)
        self.planner         = BIMExecutionPlannerAgent(provider, tool_schemas)
        self.parser          = BIMParserAgent(provider, tool_schemas)
        self.validator       = BIMValidatorAgent(provider, tool_schemas)
        self.simple_agent    = SimpleTaskAgent(provider, tool_schemas)

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(
        self,
        messages: list[dict],
        execute_tool_fn: Callable[[str, dict[str, Any]], Any],
    ) -> AsyncGenerator[dict, None]:
        """
        Drive the full agent pipeline for one user turn.

        Yields SSE-compatible dicts:
          { "type": "agent_thought" | "text_delta" | "tool_call_pending" |
                    "tool_call_executing" | "tool_result" | "error",
            ... }
        """
        history = list(messages)

        # ── Classify ──────────────────────────────────────────────────────────
        yield self._thought("[BIM Orchestrator] Classifying request...")

        try:
            classification = await self.classifier.classify(history)
        except Exception as exc:
            logger.warning("Task classification failed — defaulting to COMPLEX: %s", exc)
            classification = "COMPLEX"

        yield self._thought(f"[BIM Orchestrator] → {classification} workflow.")

        # ── Route ─────────────────────────────────────────────────────────────
        if classification == "SIMPLE":
            async for event in self._simple_flow(history, execute_tool_fn):
                yield event
        else:
            async for event in self._complex_flow(history, execute_tool_fn):
                yield event

    # ─────────────────────────────────────────────────────────────────────────
    # SIMPLE WORKFLOW
    # ─────────────────────────────────────────────────────────────────────────

    async def _simple_flow(
        self,
        history: list[dict],
        execute_tool_fn: Callable,
    ) -> AsyncGenerator[dict, None]:
        """
        Simple task pipeline:
          Phase 0 — Pre-fetch model state.
          Phase 1 — SimpleTaskAgent (tool-calling).
          Phase 2 — Post-fetch verification (for write ops).
        """

        # ── Phase 0: Pre-fetch ────────────────────────────────────────────────
        yield self._thought("[Simple Task Agent] Fetching current model state...")

        existing_state  = await fetch_existing_state(execute_tool_fn, history)
        state_summary   = format_state_summary(existing_state)

        yield self._thought(f"[Simple Task Agent] Current state:\n{state_summary}")

        # Inject state context into conversation so the agent avoids duplicates
        history_with_ctx = inject_state_context(history, existing_state)

        # ── Phase 1: SimpleTaskAgent ──────────────────────────────────────────
        yield self._thought("[Simple Task Agent] Processing request...")

        text_parts: list[str] = []
        pending_calls: list[dict] = []

        try:
            async for event in self.simple_agent.stream_turn(
                history_with_ctx, self.tool_schemas
            ):
                etype = event.get("type")
                if etype == "text_delta":
                    text_parts.append(event["content"])
                    yield event
                elif etype == "tool_call":
                    pending_calls.append({
                        "id":   str(uuid.uuid4()),
                        "name": event["name"],
                        "args": event.get("args", {}),
                    })
                elif etype == "error":
                    yield event
                elif etype == "done":
                    break
        except Exception as exc:
            yield self._error("Simple agent stream failed", str(exc))
            return

        # Dispatch collected tool calls
        for tc in pending_calls:
            cid    = tc["id"]
            t_name = tc["name"]
            args   = tc["args"]

            yield {"type": "tool_call_pending", "id": cid, "tool": t_name,
                   "args": args, "requires_approval": False}
            yield {"type": "tool_call_executing", "id": cid, "tool": t_name}

            try:
                result = await execute_tool_fn(t_name, args)
            except Exception as exc:
                result = {"status": "error", "message": str(exc)}

            yield {"type": "tool_result", "id": cid, "tool": t_name,
                   "result": result, "approved": True}

        # ── Phase 2: Post-fetch verification (write ops only) ─────────────────
        user_msg = (history[-1].get("content", "") if history else "").lower()
        is_write = (
            pending_calls
            or any(kw in user_msg for kw in ("create", "add", "make", "new",
                                               "delete", "remove", "modify", "update"))
        )

        if is_write:
            yield self._thought("[Simple Task Agent] Verifying changes in Revit...")
            post_state   = await fetch_existing_state(execute_tool_fn, history)
            post_summary = format_state_summary(post_state)
            yield self._thought(
                f"[Simple Task Agent] Post-execution state:\n{post_summary}"
            )
            yield {
                "type":    "text_delta",
                "content": (
                    "\n\n### ✅ Verification Report\n"
                    "Operation completed and verified.\n\n"
                    f"**Current model state:**\n\n{post_summary}"
                ),
            }

    # ─────────────────────────────────────────────────────────────────────────
    # COMPLEX WORKFLOW
    # ─────────────────────────────────────────────────────────────────────────

    async def _complex_flow(
        self,
        history: list[dict],
        execute_tool_fn: Callable,
    ) -> AsyncGenerator[dict, None]:
        """
        Full multi-agent pipeline for complex layout and structural tasks.
        Drives all 8 phases sequentially, yielding live SSE events throughout.
        """

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 0 — Pre-flight: fetch existing model state
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Orchestrator] Phase 0 — Fetching current model state (levels, grids, columns)..."
        )

        existing_state = await fetch_existing_state(execute_tool_fn, history)
        state_summary  = format_state_summary(existing_state)

        yield self._thought(f"[BIM Orchestrator] Model state:\n{state_summary}")

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 1 — Intent Clarification (iterate until DESIGN INTENT ESTABLISHED)
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Intent Clarifier] Phase 1 — Analysing design requirements..."
        )

        history_with_ctx = inject_state_context(history, existing_state)
        history_with_ctx = inject_schemas_context(history_with_ctx, self.tool_schemas)

        try:
            intent_response = await self.intent_clarifier.clarify(history_with_ctx)
        except Exception as exc:
            yield self._error("Intent Clarifier failed", str(exc))
            return

        if "DESIGN INTENT ESTABLISHED" not in intent_response:
            # Still iterating with user — emit response and wait for next turn
            yield {"type": "text_delta", "content": intent_response}
            return

        # Intent is fully established — show the summary to the user
        yield {"type": "text_delta", "content": intent_response}

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 2 — Input Design Manual Generation
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Design Manual] Phase 2 — Generating complete numeric Input Design Manual..."
        )

        try:
            input_design_manual = await self.manual_agent.generate_manual(
                intent_text=intent_response,
                existing_state_summary=state_summary,
            )
        except Exception as exc:
            yield self._error("Design Manual generation failed", str(exc))
            return

        yield self._thought(
            f"[BIM Design Manual] Input Design Manual compiled:\n\n{input_design_manual}"
        )

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 3 — Execution Planning
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Execution Planner] Phase 3 — Formulating execution strategy..."
        )

        try:
            execution_plan = await self.planner.create_plan(
                design_manual=input_design_manual,
                existing_state_summary=state_summary,
            )
        except Exception as exc:
            yield self._error("Execution planning failed", str(exc))
            return

        yield self._thought(
            f"[BIM Execution Planner] Execution Plan:\n{execution_plan}"
        )

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 4 — Parse Design Manual → execute_batch JSON + Dedup Filter
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Parser] Phase 4 — Translating Input Design Manual to tool-call JSON..."
        )

        try:
            batch_json_str = await self.parser.manual_to_json(
                design_manual=input_design_manual,
                existing_state_summary=state_summary,
                execution_plan=execution_plan,
            )
            batch_data = json.loads(batch_json_str)
        except json.JSONDecodeError as exc:
            yield self._error("Parser produced invalid JSON", str(exc))
            return
        except Exception as exc:
            yield self._error("Parser (forward) failed", str(exc))
            return

        # Deterministic dedup safety net — strips any duplicate create_* calls
        batch_data, dedup_report = filter_duplicate_calls(
            batch_data, existing_state
        )
        if dedup_report:
            yield self._thought(
                f"[BIM Orchestrator] Dedup filter applied:\n{dedup_report}"
            )

        n_calls = len(batch_data.get("calls", []))
        yield self._thought(
            f"[BIM Parser] Batch payload ready — {n_calls} tool call(s) to execute."
        )

        if n_calls == 0:
            yield {
                "type":    "text_delta",
                "content": (
                    "\n\n⚠️ **Nothing to create** — all requested elements already "
                    "exist in the model."
                ),
            }
            return

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 5 — Execute Batch in Revit
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Orchestrator] Phase 5 — Dispatching batch transaction to Revit..."
        )

        # Stream the tool call JSON payload so it is visible in the agent activity thoughts
        yield self._thought(
            "[BIM Orchestrator] Phase 5 — Dispatched Batch Payload:\n"
            "```json\n"
            f"{json.dumps(batch_data, indent=2)}\n"
            "```"
        )

        call_id = str(uuid.uuid4())
        yield {"type": "tool_call_pending", "id": call_id,
               "tool": "execute_batch", "args": batch_data, "requires_approval": False}
        yield {"type": "tool_call_executing", "id": call_id, "tool": "execute_batch"}

        try:
            batch_result = await execute_tool_fn("execute_batch", batch_data)
        except Exception as exc:
            batch_result = {"status": "error", "message": str(exc)}

        yield {"type": "tool_result", "id": call_id, "tool": "execute_batch",
               "result": batch_result, "approved": True}

        if batch_result.get("status") == "error":
            yield self._thought(
                f"[BIM Orchestrator] Batch transaction failed and was rolled back in Revit: {batch_result.get('message', 'Unknown error')}. "
                "Proceeding to reverse-parse results and run validation on the failures."
            )

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 6 — Reverse Parse: parser agent fetches real state → Result Design Manual
        #
        # The parser runs as a full tool-calling agent loop (AgentOrchestrator).
        # It inspects the batch result, infers which fetch_* tools to call for each
        # created element category, executes those tools, and emits the Result DM
        # as its final text.  Adding new tool types requires ZERO changes here.
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Parser] Phase 6 — Reverse-parsing: fetching actual Revit state "
            "for created elements and compiling Result Design Manual..."
        )

        # Build initial messages for the reverse-parse agent
        reverse_messages = self.parser.build_reverse_messages(
            batch_result=batch_result,
            input_design_manual=input_design_manual,
        )

        # Only fetch_* tools are permitted in this phase — filtered at runtime
        fetch_only_schemas = [
            s for s in self.tool_schemas
            if s.get("name", "").startswith("fetch_")
        ]

        # Drive the agent loop: parser makes fetch_* calls, gets results, emits Result DM
        reverse_orchestrator = AgentOrchestrator(
            provider=self.provider,
            tool_schemas=fetch_only_schemas,
            max_turns=10,
            system_prompt=self.parser.reverse_system_prompt,
        )

        result_dm_parts: list[str] = []

        async for event in reverse_orchestrator.run(
            messages=reverse_messages,
            execute_tool_fn=execute_tool_fn,
        ):
            etype = event.get("type")
            if etype == "text_delta":
                result_dm_parts.append(event["content"])
            elif etype == "agent_thought":
                yield self._thought(f"[BIM Parser] {event['content']}")
            elif etype in ("tool_call_pending", "tool_call_executing", "tool_result"):
                # Surface fetch tool calls to the UI for transparency
                yield event
            elif etype == "error":
                yield self._error("Reverse parse error", event.get("detail", event.get("content", "")))

        result_design_manual = "".join(result_dm_parts).strip()

        if not result_design_manual:
            result_design_manual = "(Result Design Manual could not be generated — fetch tools returned no data.)"

        yield self._thought(
            f"[BIM Parser] Phase 6 — Result Design Manual ready "
            f"({len(result_design_manual)} chars)."
        )
        # ══════════════════════════════════════════════════════════════════════
        # PHASE 7 — Validation: Input DM vs Result DM (real Revit data)
        # ══════════════════════════════════════════════════════════════════════
        yield self._thought(
            "[BIM Validator] Phase 7 — Validating Result Design Manual (real Revit "
            "data) against Input Design Manual..."
        )

        try:
            validation_report = await self.validator.validate(
                input_manual=input_design_manual,
                result_manual=result_design_manual,
            )
        except Exception as exc:
            yield self._error("Validation failed", str(exc))
            return

        yield {
            "type":    "text_delta",
            "content": f"\n\n### 🔍 Validation Report\n\n{validation_report}",
        }

        # ══════════════════════════════════════════════════════════════════════
        # PHASE 8 — Orchestrator Decision
        # ══════════════════════════════════════════════════════════════════════
        if "VALIDATION: PASSED" in validation_report:
            yield self._thought(
                "[BIM Orchestrator] Phase 8 — Validation passed. Pipeline complete."
            )
            yield {
                "type":    "text_delta",
                "content": (
                    "\n\n### 🏆 Execution Complete\n\n"
                    "All elements were created, fetched from Revit, and validated "
                    "against the design intent.\n\n"
                    "| Phase | Status |\n"
                    "|---|---|\n"
                    "| Phase 0 · Pre-flight state fetch | ✅ |\n"
                    "| Phase 1 · Design intent clarified | ✅ |\n"
                    "| Phase 2 · Input Design Manual compiled | ✅ |\n"
                    "| Phase 3 · Execution plan formulated | ✅ |\n"
                    "| Phase 4 · Parsed to tool-call JSON | ✅ |\n"
                    "| Phase 5 · Batch committed to Revit | ✅ |\n"
                    "| Phase 6a · Real Revit state fetched | ✅ |\n"
                    "| Phase 6b · Result Design Manual compiled | ✅ |\n"
                    "| Phase 7 · Validation passed | ✅ |\n"
                ),
            }
        else:
            yield self._thought(
                "[BIM Orchestrator] Phase 8 — Validation reported issues. "
                "Surfacing to user for review."
            )
            yield {
                "type":    "text_delta",
                "content": (
                    "\n\n### ⚠️ Validation Issues Detected\n\n"
                    "One or more elements do not match the design intent when "
                    "compared against actual Revit data. "
                    "Please review the Validation Report above.\n\n"
                    "You can request corrections or a retry with adjusted parameters."
                ),
            }

        yield self._thought("[BIM Orchestrator] Multi-agent pipeline finished.")

    # ─────────────────────────────────────────────────────────────────────────
    # SSE event factory helpers (keep yielded dicts consistent)
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _thought(content: str) -> dict:
        """Emit an agent_thought SSE event."""
        return {"type": "agent_thought", "content": content}

    @staticmethod
    def _error(message: str, detail: str = "") -> dict:
        """Emit an error SSE event."""
        return {"type": "error", "content": message, "detail": detail}
