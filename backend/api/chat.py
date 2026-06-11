# -*- coding: utf-8 -*-
"""
Chat API — Streaming conversation endpoint with direct DB queries and decoupled agent loop.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from config import get_settings
from providers import get_provider
from services.streaming import SSEEventBuilder
from services.tool_registry import registry
from core.agent_loop import AgentOrchestrator
from infra.db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    provider: str | None = None
    model: str | None = None

    @field_validator("model", mode="before")
    @classmethod
    def _coerce_model(cls, v):
        if v is None:
            return None
        if not isinstance(v, str):
            return None
        if "[object" in v:
            return None
        return v.strip() or None

# Dependency to get Database client from application state
def get_db(request: Request) -> Database:
    return request.app.state.db

# ─────────────────────────────────────────────────────────────────────────────
# POST /api/chat
# ─────────────────────────────────────────────────────────────────────────────

@router.post("")
async def chat(body: ChatRequest, request: Request, db: Database = Depends(get_db)):
    """Starts an agent turn for the given session and returns SSE stream."""
    # ── 1. Validate session ───────────────────────────────────────────────
    session = await db.get_session(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{body.session_id}' not found.")

    # ── 2. Resolve provider settings ──────────────────────────────────────
    settings = get_settings()

    # Dynamic check to ensure the tool registry is initialized
    if not registry.schemas:
        await registry.ensure_loaded(request.app.state.revit_bridge)

    provider_name, model, api_key = await _resolve_provider(body, db, settings)

    try:
        provider = get_provider(provider_name, api_key=api_key, model=model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── 3. Load and map message history ───────────────────────────────────
    db_messages = await db.get_session_messages(body.session_id)
    history = db_messages_to_history(db_messages)

    # ── 4. Save user message ──────────────────────────────────────────────
    user_msg_id = str(uuid.uuid4())
    await db.save_message(
        message_id=user_msg_id,
        session_id=body.session_id,
        role="user",
        content=body.message
    )

    history.append({"role": "user", "content": body.message})

    # ── 5. Setup SSE Stream ───────────────────────────────────────────────
    message_id = str(uuid.uuid4())
    session_id = body.session_id
    tool_schemas = registry.schemas

    async def execute_tool_callback(tool_name: str, args: dict) -> dict:
        dispatcher = registry.get_dispatcher(tool_name)
        if dispatcher is None:
            await registry.ensure_loaded(request.app.state.revit_bridge, force=True)
            dispatcher = registry.get_dispatcher(tool_name)
        
        if dispatcher is None:
            return {
                "status": "error",
                "message": f"Tool '{tool_name}' is not registered on the Revit bridge."
            }
        return await dispatcher(**args)

    async def event_generator():
        accumulated_text: list[str] = []
        tc_map: dict[str, dict] = {}
        accumulated_thoughts: list[str] = []

        orchestrator = AgentOrchestrator(
            provider=provider,
            tool_schemas=tool_schemas,
            max_turns=settings.agent_max_turns
        )

        try:
            async for event in orchestrator.run(
                messages=history,
                execute_tool_fn=execute_tool_callback
            ):
                # Detect client disconnect and stop generator
                if await request.is_disconnected():
                    logger.info("Client disconnected. Cancelling agent stream.")
                    break

                etype = event.get("type")
                if etype == "text_delta":
                    content = event.get("content", "")
                    accumulated_text.append(content)
                    yield SSEEventBuilder.text_delta(content)
                elif etype == "agent_thought":
                    content = event.get("content", "")
                    accumulated_thoughts.append(content)
                    yield SSEEventBuilder.agent_thought(content)
                elif etype == "tool_call_pending":
                    tc_id = event.get("id", "")
                    tc_map[tc_id] = {
                        "id": tc_id,
                        "name": event.get("tool", ""),
                        "args": event.get("args", {}),
                        "status": "pending"
                    }
                    yield SSEEventBuilder.tool_call_pending(
                        call_id=tc_id,
                        tool_name=event.get("tool", ""),
                        args=event.get("args", {}),
                        requires_approval=False
                    )
                elif etype == "tool_call_executing":
                    tc_id = event.get("id", "")
                    if tc_id in tc_map:
                        tc_map[tc_id]["status"] = "executing"
                    yield SSEEventBuilder.tool_call_executing(
                        call_id=tc_id,
                        tool_name=event.get("tool", "")
                    )
                elif etype == "tool_result":
                    tc_id = event.get("id", "")
                    if tc_id in tc_map:
                        tc_map[tc_id]["status"] = "done"
                        tc_map[tc_id]["result"] = event.get("result")
                        tc_map[tc_id]["approved"] = True
                    yield SSEEventBuilder.tool_result(
                        call_id=tc_id,
                        tool_name=event.get("tool", ""),
                        result=event.get("result", {}),
                        approved=True
                    )
                elif etype == "error":
                    yield SSEEventBuilder.error(
                        message=event.get("content", ""),
                        detail=event.get("detail", "")
                    )

            # Send done event at the end
            yield SSEEventBuilder.done(session_id=session_id, message_id=message_id)

        except Exception as exc:
            logger.exception("Unhandled error in agent loop execution")
            yield SSEEventBuilder.error("Internal agent error.", detail=str(exc))
            yield SSEEventBuilder.done(session_id=session_id, message_id=message_id)
        finally:
            # ── Persist assistant progress to database ────────────────────
            full_text = "".join(accumulated_text).strip()
            accumulated_tool_calls = list(tc_map.values())
            if full_text or accumulated_tool_calls:
                try:
                    # Save assistant message
                    await db.save_message(
                        message_id=message_id,
                        session_id=session_id,
                        role="assistant",
                        content=full_text,
                        tool_calls=json.dumps(accumulated_tool_calls) if accumulated_tool_calls else None,
                        agent_thoughts=json.dumps(accumulated_thoughts) if accumulated_thoughts else None
                    )

                    # Save tool messages (observations)
                    for tc in accumulated_tool_calls:
                        tc_id = tc.get("id", "")
                        tc_name = tc.get("name", "unknown")
                        tc_result = tc.get("result")
                        result_content = json.dumps(tc_result) if tc_result is not None else "{}"
                        await db.save_message(
                            session_id=session_id,
                            role="tool",
                            content=result_content,
                            tool_name=tc_name,
                            tool_call_id=tc_id,
                            approved=True
                        )
                    logger.debug("Successfully saved assistant messages and tool calls for session %s", session_id)
                except Exception as save_exc:
                    logger.error("Failed to persist stream messages: %s", save_exc, exc_info=True)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_provider(
    body: ChatRequest,
    db: Database,
    settings
) -> tuple[str, str, str]:
    """Resolves model and API key configuration (Gemini-only active)."""
    provider_name = "gemini"

    # Fetch configuration from the database
    cfg = await db.get_provider_config("gemini")
    active_model = cfg.get("active_model") if cfg else None
    api_key = cfg.get("api_key") if cfg else None

    # Determine dynamic settings defaults
    model = body.model or active_model or settings.default_model
    if not isinstance(model, str) or "[object" in model or not model.strip():
        model = settings.default_model
    model = model.strip()

    env_key = getattr(settings, "gemini_api_key", "")
    resolved_api_key = api_key or env_key

    if not resolved_api_key:
        raise HTTPException(
            status_code=422,
            detail="No API key configured for Google Gemini. Please set it in Settings or your .env file."
        )

    return provider_name, model, resolved_api_key

def db_messages_to_history(db_messages: list[dict]) -> list[dict]:
    """Maps database message records to provider-agnostic dictionary history."""
    tc_lookup: dict[str, dict] = {}
    for msg in db_messages:
        if msg["role"] == "assistant" and msg["tool_calls"]:
            try:
                for tc in json.loads(msg["tool_calls"]):
                    tc_id = tc.get("id", "")
                    if tc_id:
                        tc_lookup[tc_id] = tc
            except json.JSONDecodeError:
                pass

    pending_tc_list: list[dict] = []
    tool_result_idx = 0

    history = []
    for msg in db_messages:
        entry: dict = {"role": msg["role"], "content": msg["content"]}

        if msg["tool_calls"]:
            try:
                tcs = json.loads(msg["tool_calls"])
                for tc in tcs:
                    if isinstance(tc.get("args"), str):
                        try:
                            tc["args"] = json.loads(tc["args"])
                        except (json.JSONDecodeError, TypeError):
                            tc["args"] = {}
                entry["tool_calls"] = tcs
                pending_tc_list = tcs
                tool_result_idx = 0
            except json.JSONDecodeError:
                entry["tool_calls"] = []

        if msg["role"] == "tool":
            if msg["tool_name"]:
                entry["name"] = msg["tool_name"]

            # Direct ID lookup
            if msg["tool_call_id"] and msg["tool_call_id"] in tc_lookup:
                entry["tool_call_id"] = msg["tool_call_id"]
                if not entry.get("name"):
                    entry["name"] = tc_lookup[msg["tool_call_id"]].get("name", "unknown")

            # Positional fallback (legacy rows)
            elif pending_tc_list and tool_result_idx < len(pending_tc_list):
                legacy_tc = pending_tc_list[tool_result_idx]
                if not entry.get("name"):
                    entry["name"] = legacy_tc.get("name", "unknown")
                if not entry.get("tool_call_id"):
                    entry["tool_call_id"] = legacy_tc.get("id", "")
                tool_result_idx += 1

        history.append(entry)
    return history
