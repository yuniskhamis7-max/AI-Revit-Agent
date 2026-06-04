# -*- coding: utf-8 -*-
"""
Agent Service — Provider-agnostic agentic loop with human-in-the-loop approval.

This is the core orchestration layer. It drives the multi-turn conversation
with any AI provider, manages tool execution, and enforces the approval gate
for action tools.

Architecture:
  - Runs as an async generator, yielding SSE-ready event strings
  - Pauses on action tools, waits for an asyncio.Event to be set externally
  - The approval decision is passed in via an ApprovalGate dataclass
  - DEVELOPMENT_MODE=true bypasses the gate entirely (auto-approve all tools)

The agent service is stateless per-turn — conversation history is passed in
and returned out, stored in SQLite by the chat API route.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncGenerator

from config import get_settings
from providers.base import AIProvider, SYSTEM_PROMPT
from services import streaming as sse
from services.tool_registry import registry, requires_approval

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Approval Gate
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ApprovalGate:
    """
    Shared state between the agent coroutine and the /approve endpoint.

    The agent coroutine writes pending_tool_id and awaits the event.
    The HTTP handler reads pending_tool_id, sets approved, then fires the event.
    """
    event: asyncio.Event = field(default_factory=asyncio.Event)
    pending_tool_id: str | None = None
    approved: bool | None = None

    def reset(self) -> None:
        self.event.clear()
        self.pending_tool_id = None
        self.approved = None

    async def wait_for_decision(self) -> bool:
        """Blocks until the external HTTP handler calls decide()."""
        await self.event.wait()
        return bool(self.approved)

    def decide(self, approved: bool) -> None:
        """Called by POST /api/chat/approve to unblock the agent."""
        self.approved = approved
        self.event.set()


# ─────────────────────────────────────────────────────────────────────────────
# In-flight session registry
# ─────────────────────────────────────────────────────────────────────────────
# Maps session_id -> ApprovalGate. Stored in process memory — acceptable for
# local single-user deployment. Cloud deployment would use Redis pub/sub here.

_active_gates: dict[str, ApprovalGate] = {}


def get_gate(session_id: str) -> ApprovalGate | None:
    return _active_gates.get(session_id)


def create_gate(session_id: str) -> ApprovalGate:
    gate = ApprovalGate()
    _active_gates[session_id] = gate
    return gate


def remove_gate(session_id: str) -> None:
    _active_gates.pop(session_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Loop
# ─────────────────────────────────────────────────────────────────────────────

async def run_agent_stream(
    provider: AIProvider,
    messages: list[dict],
    session_id: str,
    message_id: str,
    gate: ApprovalGate,
) -> AsyncGenerator[str, None]:
    """
    Drives the agentic multi-turn loop and yields SSE event strings.

    Args:
        provider:   Instantiated AIProvider adapter.
        messages:   Full conversation history (provider-agnostic format).
        session_id: Used in the final 'done' SSE event.
        message_id: Used in the final 'done' SSE event.
        gate:       ApprovalGate — the agent writes here when pausing.

    Yields:
        SSE-formatted strings (each ending with \\n\\n), ready to stream.

    The caller (chat.py route) is responsible for:
        - Persisting the returned message history to SQLite
        - Removing the gate from _active_gates after the stream ends
    """
    settings = get_settings()
    auto_approve = settings.development_mode

    # ── Ensure the tool registry is populated ─────────────────────────────
    # If the bridge wasn't reachable at backend startup (e.g. Revit started
    # later), this triggers a lazy re-discovery before the agent loop runs.
    if not registry.schemas:
        await registry.ensure_loaded()

    tool_schemas = registry.schemas

    # Working copy of history — we append to this across turns
    history = list(messages)

    MAX_TURNS = 20
    turn = 0

    while turn < MAX_TURNS:
        turn += 1
        logger.debug("Agent turn %d", turn)

        # Emit synthetic agent-thought (not the model's internal CoT)
        if turn == 1:
            yield sse.agent_thought(
                f"[agent thought] Analyzing user request and planning response (turn {turn})..."
            )
        else:
            yield sse.agent_thought(
                f"[agent thought] Processing tool results and planning next step (turn {turn})..."
            )

        # ── Run one model inference ───────────────────────────────────────
        text_parts: list[str] = []
        pending_tool_calls: list[dict] = []

        # Buffer for detecting [object Object] split across text_delta chunks
        _OBJ_ARTIFACT = "[object Object]"
        _text_buffer = ""  # Holds trailing chars that might be a partial artifact

        async for event in provider.stream_agent_turn(
            messages=history,
            tool_schemas=tool_schemas,
            system_prompt=SYSTEM_PROMPT,
        ):
            etype = event.get("type")

            if etype == "text_delta":
                raw_text = event["content"]
                # Prepend buffer from previous delta to catch split artifacts
                combined = _text_buffer + raw_text
                # Strip all complete [object Object] occurrences
                clean_text = combined.replace(_OBJ_ARTIFACT, "")
                # Keep a tail buffer (length of artifact - 1) for next iteration
                buf_len = len(_OBJ_ARTIFACT) - 1
                if len(clean_text) > buf_len:
                    _text_buffer = clean_text[-buf_len:]
                    emit_text = clean_text[:-buf_len]
                else:
                    _text_buffer = clean_text
                    emit_text = ""
                if emit_text:
                    text_parts.append(emit_text)
                    yield sse.text_delta(emit_text)

            elif etype == "thinking_delta":
                # Suppress the model's internal chain-of-thought reasoning.
                # We emit our own synthetic [agent thought] events instead.
                pass

            elif etype == "tool_call":
                # Give each tool call a stable unique ID for the frontend
                call_id = str(uuid.uuid4())
                tc = {
                    "id": call_id,
                    "name": event["name"],
                    "args": event.get("args", {}),
                    "provider_id": event.get("id", call_id),  # Provider's own ID
                    "thought_signature": event.get("thought_signature"),  # Gemini 2.5 thinking
                }
                pending_tool_calls.append(tc)

            elif etype == "error":
                yield sse.error(event.get("content", "Unknown provider error"))

            elif etype == "done":
                break

        # ── Flush the text buffer ─────────────────────────────────────────
        # Any remaining content in the buffer is safe to emit (no partial artifact)
        _text_buffer = _text_buffer.replace(_OBJ_ARTIFACT, "")
        if _text_buffer:
            text_parts.append(_text_buffer)
            yield sse.text_delta(_text_buffer)
            _text_buffer = ""

        # ── Store assistant turn in history ───────────────────────────────
        full_text = "".join(text_parts)
        assistant_msg: dict = {
            "role": "assistant",
            "content": full_text,
            "tool_calls": [
                {"id": tc["provider_id"], "name": tc["name"], "args": tc["args"],
                 "thought_signature": tc.get("thought_signature")}
                for tc in pending_tool_calls
            ],
        }
        history.append(assistant_msg)

        # ── If no tool calls, we're done ──────────────────────────────────
        if not pending_tool_calls:
            break

        # ── Process each tool call ────────────────────────────────────────
        for tc in pending_tool_calls:
            call_id   = tc["id"]
            tool_name = tc["name"]
            args      = tc["args"]
            needs_approval = requires_approval(tool_name)

            # Emit agent thought describing the tool call with its JSON payload
            args_summary = json.dumps(args, ensure_ascii=False)
            yield sse.agent_thought(
                f"[agent thought] Calling tool: {tool_name}({args_summary})"
            )

            # Emit pending event (always — frontend shows the card)
            yield sse.tool_call_pending(
                call_id=call_id,
                tool_name=tool_name,
                args=args,
                requires_approval=needs_approval and not auto_approve,
            )

            # ── Approval gate ─────────────────────────────────────────────
            approved: bool | None = None

            if needs_approval and not auto_approve:
                # Signal the frontend that we're waiting
                gate.reset()
                gate.pending_tool_id = call_id
                yield sse.agent_paused(awaiting_id=call_id, tool_name=tool_name)

                logger.info(
                    "Agent paused — awaiting approval for '%s' (%s)", tool_name, call_id
                )
                approved = await gate.wait_for_decision()
                logger.info("Approval decision for '%s': %s", call_id, approved)

                if not approved:
                    # User rejected — feed a rejection observation back to model
                    rejection_result = {
                        "status": "rejected",
                        "message": (
                            f"The user rejected the '{tool_name}' action. "
                            "Do not retry it. Ask the user how they would like to proceed."
                        ),
                    }
                    yield sse.tool_result(
                        call_id=call_id, tool_name=tool_name,
                        result=rejection_result, approved=False,
                    )
                    history.append({
                        "role": "tool",
                        "name": tool_name,
                        "tool_call_id": tc["provider_id"],
                        "content": json.dumps(rejection_result),
                    })
                    yield sse.agent_thought(
                        f"[agent thought] Tool {tool_name} was rejected by user."
                    )
                    continue  # Process next tool call (or let model respond to rejection)
            else:
                # Auto-approve (fetch tool or DEVELOPMENT_MODE)
                approved = True

            # ── Execute the tool ──────────────────────────────────────────
            yield sse.tool_call_executing(call_id=call_id, tool_name=tool_name)

            dispatcher = registry.get_dispatcher(tool_name)

            # ── Lazy re-discovery: if the tool isn't registered, the registry
            # may be stale (bridge started after backend, or dev mode returned
            # empty tools). Try re-discovering once before giving up.
            if dispatcher is None and not registry.schemas:
                reloaded = await registry.ensure_loaded(force=True)
                if reloaded:
                    dispatcher = registry.get_dispatcher(tool_name)

            if dispatcher is None:
                result = {
                    "status": "error",
                    "message": (
                        f"Tool '{tool_name}' is not available. "
                        f"The bridge has {len(registry.schemas)} tool(s) registered: "
                        f"{registry.tool_names() or 'none'}. "
                        "If the Revit bridge was recently restarted, try refreshing tools "
                        "or restarting the backend."
                    ),
                }
            else:
                result = await dispatcher(**args)

            # Emit agent thought with the tool result payload
            result_summary = json.dumps(result, ensure_ascii=False)
            yield sse.agent_thought(
                f"[agent thought] Tool {tool_name} returned: {result_summary}"
            )

            # Log tool errors and warnings for debugging
            result_status = result.get("status", "unknown")
            if result_status == "error":
                logger.error(
                    "Tool '%s' returned error: %s",
                    tool_name, result.get("message", "unknown"),
                )
            tool_warnings = result.get("warnings")
            if tool_warnings:
                logger.warning(
                    "Tool '%s' warnings (%d): %s",
                    tool_name, len(tool_warnings), tool_warnings,
                )
            tool_errors = result.get("errors")
            if tool_errors:
                logger.error(
                    "Tool '%s' errors (%d): %s",
                    tool_name, len(tool_errors), tool_errors,
                )

            yield sse.tool_result(
                call_id=call_id, tool_name=tool_name, result=result, approved=approved
            )

            # Append tool result to history for next model turn
            history.append({
                "role": "tool",
                "name": tool_name,
                "tool_call_id": tc["provider_id"],
                "content": json.dumps(result),
            })

    # ── All turns complete ────────────────────────────────────────────────
    if turn >= MAX_TURNS:
        yield sse.error(
            "Agent exceeded maximum turn limit.", detail=f"MAX_TURNS={MAX_TURNS}"
        )

    yield sse.done(session_id=session_id, message_id=message_id)
