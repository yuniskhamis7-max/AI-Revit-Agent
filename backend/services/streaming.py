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
    """Serialises a dict to an SSE data line (RFC 8895 format)."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# Event factories
# ─────────────────────────────────────────────────────────────────────────────

def text_delta(content: str) -> str:
    return _event({"type": "text_delta", "content": content})


def thinking_delta(content: str) -> str:
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
    return _event({
        "type": "tool_call_pending",
        "id": call_id,
        "tool": tool_name,
        "args": args,
        "requires_approval": requires_approval,
    })


def tool_call_executing(call_id: str, tool_name: str) -> str:
    return _event({"type": "tool_call_executing", "id": call_id, "tool": tool_name})


def tool_result(call_id: str, tool_name: str, result: dict, approved: bool | None = None) -> str:
    return _event({
        "type": "tool_result",
        "id": call_id,
        "tool": tool_name,
        "result": result,
        "approved": approved,
    })


def agent_paused(awaiting_id: str, tool_name: str) -> str:
    return _event({
        "type": "agent_paused",
        "awaiting_approval_id": awaiting_id,
        "tool": tool_name,
    })


def error(message: str, detail: str = "") -> str:
    return _event({"type": "error", "message": message, "detail": detail})


def done(session_id: str, message_id: str) -> str:
    return _event({"type": "done", "session_id": session_id, "message_id": message_id})
