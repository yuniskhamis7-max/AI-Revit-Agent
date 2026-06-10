# -*- coding: utf-8 -*-
"""
SSE Streaming Helpers — Factory functions for building typed Server-Sent Event
payloads. Every event in the system is created through this module to ensure
the frontend can rely on a stable, consistent event contract.

SSE event types (sent as JSON in the `data:` field):
  text_delta         — incremental assistant text chunk
  tool_call_pending  — agent wants to call a tool (may require approval)
  tool_call_executing— tool call approved and about to run
  tool_result        — tool execution completed (result or rejection)
  agent_paused       — agent is waiting for human approval
  error              — unrecoverable error during agent execution
  done               — agent turn complete
"""
from __future__ import annotations

import json
from typing import Any


def _event(payload: dict) -> str:
    """
    Serialise a dict to an SSE data line following RFC 8895 format.

    Args:
        payload: Dictionary to JSON-encode into the SSE data field.

    Returns:
        str: Formatted SSE string, e.g. 'data: {"type": "text_delta", ...}\\n\\n'
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# Event factories
# ─────────────────────────────────────────────────────────────────────────────

def text_delta(content: str) -> str:
    """
    Emit an incremental text chunk from the AI assistant.

    Args:
        content: Partial text to append to the assistant's response.

    Returns:
        str: SSE event string with type='text_delta'.
    """
    return _event({"type": "text_delta", "content": content})


def thinking_delta(content: str) -> str:
    """
    Emit a chunk of the model's internal chain-of-thought reasoning.

    Currently suppressed by the agent loop — reserved for future use.

    Args:
        content: Partial thinking text from the model.

    Returns:
        str: SSE event string with type='thinking_delta'.
    """
    return _event({"type": "thinking_delta", "content": content})


def agent_thought(content: str) -> str:
    """
    Emits a synthetic agent-thought event for the frontend to display.
    These are NOT the model's internal chain-of-thought — they are human-readable
    status messages that mirror what was previously logged in the console, e.g.
      '[agent thought] Analyzing user request...'
      '[agent thought] Calling tool: fetch_levels({...})'
    """
    return _event({"type": "agent_thought", "content": content})


def tool_call_pending(
    call_id: str,
    tool_name: str,
    args: dict[str, Any],
    requires_approval: bool,
) -> str:
    """
    Emit a tool call request from the agent.

    Sent when the model decides to call a tool. The frontend renders a tool
    call card. If requires_approval is True, the agent is paused until the
    user responds via POST /api/chat/approve.

    Args:
        call_id:           Unique UUID assigned to this tool call instance.
        tool_name:         Name of the tool to execute (e.g. 'fetch_levels').
        args:              Arguments dict to pass to the tool.
        requires_approval: True if this is a write tool needing human approval.

    Returns:
        str: SSE event string with type='tool_call_pending'.
    """
    return _event({
        "type": "tool_call_pending",
        "id": call_id,
        "tool": tool_name,
        "args": args,
        "requires_approval": requires_approval,
    })


def tool_call_executing(call_id: str, tool_name: str) -> str:
    """
    Emit when a tool call has been approved and is about to execute.

    Signals the frontend to update the tool card status to 'executing'.

    Args:
        call_id:   UUID of the tool call now running.
        tool_name: Name of the tool being executed.

    Returns:
        str: SSE event string with type='tool_call_executing'.
    """
    return _event({"type": "tool_call_executing", "id": call_id, "tool": tool_name})


def tool_result(call_id: str, tool_name: str, result: dict, approved: bool | None = None) -> str:
    """
    Emit the result of a completed tool execution.

    Sent after the tool finishes (success, error, or user rejection).
    The frontend updates the tool card with the result payload.

    Args:
        call_id:   UUID of the completed tool call.
        tool_name: Name of the tool that was executed.
        result:    Tool execution result dict. Contains at minimum a 'status' key.
        approved:  True if user approved, False if rejected, None for auto-approved tools.

    Returns:
        str: SSE event string with type='tool_result'.
    """
    return _event({
        "type": "tool_result",
        "id": call_id,
        "tool": tool_name,
        "result": result,
        "approved": approved,
    })


def agent_paused(awaiting_id: str, tool_name: str) -> str:
    """
    Emit when the agent is paused waiting for human approval on a tool call.

    The frontend uses this to show the approval modal overlay. The agent
    coroutine is blocked on ApprovalGate.wait_for_decision() until the
    user responds.

    Args:
        awaiting_id: UUID of the tool call awaiting approval.
        tool_name:   Name of the tool that requires approval.

    Returns:
        str: SSE event string with type='agent_paused'.
    """
    return _event({
        "type": "agent_paused",
        "awaiting_approval_id": awaiting_id,
        "tool": tool_name,
    })


def error(message: str, detail: str = "") -> str:
    """
    Emit an unrecoverable error that occurred during agent execution.

    The frontend displays this as a warning message in the chat. The agent
    turn is considered complete after this event.

    Args:
        message: Human-readable error description.
        detail:  Optional technical detail string (e.g. stack trace summary).

    Returns:
        str: SSE event string with type='error'.
    """
    return _event({"type": "error", "message": message, "detail": detail})


def done(session_id: str, message_id: str) -> str:
    """
    Emit the terminal event signalling the agent turn is complete.

    The frontend uses this to finalise the streaming message (assign the
    persistent message ID and stop the streaming cursor).

    Args:
        session_id: UUID of the session this turn belongs to.
        message_id: UUID assigned to the persisted assistant message.

    Returns:
        str: SSE event string with type='done'.
    """
    return _event({"type": "done", "session_id": session_id, "message_id": message_id})
