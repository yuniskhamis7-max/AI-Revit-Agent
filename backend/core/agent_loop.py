# -*- coding: utf-8 -*-
"""
Agent Loop — Provider-agnostic orchestration loop.

Coordinates LLM reasoning turns and tool executions. Communicates exclusively
using raw Python dictionaries at layer boundaries.
"""
from __future__ import annotations

import logging
import uuid
from typing import AsyncGenerator, Any, Callable
from providers.base import AIProvider, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """
    Orchestrates multi-turn conversation reasoning and tool execution.

    Keeps references to the LLM provider, schemas, and turn limits encapsulated.
    """
    def __init__(self, provider: AIProvider, tool_schemas: list[dict], max_turns: int = 20):
        self.provider = provider
        self.tool_schemas = tool_schemas
        self.max_turns = max_turns

    async def run(
        self,
        messages: list[dict],
        execute_tool_fn: Callable[[str, dict[str, Any]], Any]
    ) -> AsyncGenerator[dict, None]:
        """
        Executes the multi-turn agent loop.

        Args:
            messages:        List of chat history messages in provider-agnostic format:
                             [{"role": "user"|"assistant"|"tool", "content": "..."}]
            execute_tool_fn: Async callback to execute a tool: (tool_name, args) -> result_dict

        Yields:
            Event dictionaries containing event type and payloads.
        """
        # Working copy of conversation history
        history = list(messages)
        turn = 0

        while turn < self.max_turns:
            turn += 1
            logger.debug("Agent loop turn %d", turn)

            # Emit agent status thought
            if turn == 1:
                yield {
                    "type": "agent_thought",
                    "content": f"[agent thought] Analyzing user request and planning response (turn {turn})..."
                }
            else:
                yield {
                    "type": "agent_thought",
                    "content": f"[agent thought] Processing tool results and planning next step (turn {turn})..."
                }

            # ── Run model inference ──────────────────────────────────────────
            text_parts: list[str] = []
            pending_tool_calls: list[dict] = []

            # Filter JS-style [object Object] artifacts from streaming responses
            _OBJ_ARTIFACT = "[object Object]"
            _text_buffer = ""

            try:
                async for event in self.provider.stream_agent_turn(
                    messages=history,
                    tool_schemas=self.tool_schemas,
                    system_prompt=SYSTEM_PROMPT,
                ):
                    etype = event.get("type")

                    if etype == "text_delta":
                        raw_text = event["content"]
                        combined = _text_buffer + raw_text
                        clean_text = combined.replace(_OBJ_ARTIFACT, "")
                        
                        buf_len = len(_OBJ_ARTIFACT) - 1
                        if len(clean_text) > buf_len:
                            _text_buffer = clean_text[-buf_len:]
                            emit_text = clean_text[:-buf_len]
                        else:
                            _text_buffer = clean_text
                            emit_text = ""
                        
                        if emit_text:
                            text_parts.append(emit_text)
                            yield {"type": "text_delta", "content": emit_text}

                    elif etype == "thinking_delta":
                        # Suppress LLM's internal CoT delta
                        pass

                    elif etype == "tool_call":
                        call_id = str(uuid.uuid4())
                        tc = {
                            "id": call_id,
                            "name": event["name"],
                            "args": event.get("args", {}),
                            "provider_id": event.get("id", call_id),
                            "thought_signature": event.get("thought_signature"),
                        }
                        pending_tool_calls.append(tc)

                    elif etype == "error":
                        yield {"type": "error", "content": event.get("content", "Unknown provider error")}

                    elif etype == "done":
                        break

            except Exception as exc:
                logger.exception("Error during LLM stream generation")
                yield {"type": "error", "content": "Model execution failed", "detail": str(exc)}
                break

            # Flush text buffer
            _text_buffer = _text_buffer.replace(_OBJ_ARTIFACT, "")
            if _text_buffer:
                text_parts.append(_text_buffer)
                yield {"type": "text_delta", "content": _text_buffer}

            # Store assistant response in history
            full_text = "".join(text_parts)
            assistant_msg = {
                "role": "assistant",
                "content": full_text,
                "tool_calls": [
                    {
                        "id": tc["provider_id"],
                        "name": tc["name"],
                        "args": tc["args"],
                        "thought_signature": tc.get("thought_signature")
                    }
                    for tc in pending_tool_calls
                ],
            }
            history.append(assistant_msg)

            # Stop if no tool calls are requested by the model
            if not pending_tool_calls:
                break

            # ── Execute Tool Calls ───────────────────────────────────────────
            for tc in pending_tool_calls:
                call_id = tc["id"]
                tool_name = tc["name"]
                args = tc["args"]

                yield {
                    "type": "agent_thought",
                    "content": f"[agent thought] Calling tool: {tool_name}({args})"
                }

                yield {
                    "type": "tool_call_pending",
                    "id": call_id,
                    "tool": tool_name,
                    "args": args,
                    "requires_approval": False
                }

                yield {
                    "type": "tool_call_executing",
                    "id": call_id,
                    "tool": tool_name
                }

                # Execute tool directly (auto-approved)
                try:
                    result = await execute_tool_fn(tool_name, args)
                except Exception as exc:
                    result = {
                        "status": "error",
                        "message": f"Execution wrapper exception: {str(exc)}"
                    }

                yield {
                    "type": "agent_thought",
                    "content": f"[agent thought] Tool {tool_name} returned: {_summarize_result(result)}"
                }

                yield {
                    "type": "tool_result",
                    "id": call_id,
                    "tool": tool_name,
                    "result": result,
                    "approved": True
                }

                # Append tool result to history for next model turn
                history.append({
                    "role": "tool",
                    "name": tool_name,
                    "tool_call_id": tc["provider_id"],
                    "content": str(result) if not isinstance(result, dict) else _json_dumps(result)
                })

        if turn >= self.max_turns:
            yield {"type": "error", "content": "Agent exceeded maximum turn limit"}


def _summarize_result(result: Any) -> str:
    """Creates a clean, human-readable summary of a tool result dictionary."""
    if not isinstance(result, dict):
        val = str(result)
        return val[:200] + "..." if len(val) > 200 else val

    status = result.get("status")
    message = result.get("message")
    summary_parts = []
    if status:
        summary_parts.append(f"status='{status}'")
    if message:
        summary_parts.append(f"message='{message}'")

    # Check for lists in data to summarize count
    data = result.get("data")
    if isinstance(data, dict):
        counts = []
        for k, v in data.items():
            if isinstance(v, list):
                counts.append(f"{len(v)} {k}")
        if counts:
            summary_parts.append(f"data=({', '.join(counts)})")

    if not summary_parts:
        # Fallback to a truncated string representation of the dict
        val = str(result)
        return val[:200] + "..." if len(val) > 200 else val

    return ", ".join(summary_parts)


def _json_dumps(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj)
    except Exception:
        return str(obj)
