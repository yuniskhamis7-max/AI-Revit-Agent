# -*- coding: utf-8 -*-
"""
SSE Streaming Helpers — Factory class for building typed Server-Sent Event payloads.
"""
from __future__ import annotations

import json
from typing import Any


class SSEEventBuilder:
    """
    Builder class to construct standard SSE payloads for the frontend client.
    """
    @staticmethod
    def _event(payload: dict) -> str:
        """Serialise a dict to an SSE data line following RFC 8895 format."""
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @classmethod
    def text_delta(cls, content: str) -> str:
        """Emit an incremental text chunk from the AI assistant."""
        return cls._event({"type": "text_delta", "content": content})

    @classmethod
    def thinking_delta(cls, content: str) -> str:
        """Emit a chunk of the model's internal chain-of-thought reasoning."""
        return cls._event({"type": "thinking_delta", "content": content})

    @classmethod
    def agent_thought(cls, content: str) -> str:
        """Emits a synthetic agent-thought event for status logging."""
        return cls._event({"type": "agent_thought", "content": content})

    @classmethod
    def tool_call_pending(
        cls,
        call_id: str,
        tool_name: str,
        args: dict[str, Any],
        requires_approval: bool = False,
    ) -> str:
        """Emit a tool call request from the agent."""
        return cls._event({
            "type": "tool_call_pending",
            "id": call_id,
            "tool": tool_name,
            "args": args,
            "requires_approval": requires_approval,
        })

    @classmethod
    def tool_call_executing(cls, call_id: str, tool_name: str) -> str:
        """Emit when a tool call has been approved and is about to execute."""
        return cls._event({"type": "tool_call_executing", "id": call_id, "tool": tool_name})

    @classmethod
    def tool_result(cls, call_id: str, tool_name: str, result: dict, approved: bool | None = None) -> str:
        """Emit the result of a completed tool execution."""
        return cls._event({
            "type": "tool_result",
            "id": call_id,
            "tool": tool_name,
            "result": result,
            "approved": approved,
        })

    @classmethod
    def agent_paused(cls, awaiting_id: str, tool_name: str) -> str:
        """Emit when the agent is paused waiting for human approval."""
        return cls._event({
            "type": "agent_paused",
            "awaiting_approval_id": awaiting_id,
            "tool": tool_name,
        })

    @classmethod
    def error(cls, message: str, detail: str = "") -> str:
        """Emit an unrecoverable error that occurred during agent execution."""
        return cls._event({"type": "error", "message": message, "detail": detail})

    @classmethod
    def done(cls, session_id: str, message_id: str) -> str:
        """Emit the terminal event signalling the agent turn is complete."""
        return cls._event({"type": "done", "session_id": session_id, "message_id": message_id})
