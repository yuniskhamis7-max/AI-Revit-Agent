# -*- coding: utf-8 -*-
"""
Chat API — Streaming conversation endpoint with human-in-the-loop approval.

Routes:
  POST /api/chat          — start an agent turn, returns SSE stream
  POST /api/chat/approve  — approve or reject a pending tool call
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db, AsyncSessionLocal
from models import Message, ProviderConfig, Session
from providers import get_provider
from services import streaming as sse
from services.agent import (
    create_gate,
    get_gate,
    remove_gate,
    run_agent_stream,
)
from services.tool_registry import registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str
    message: str
    provider: str | None = None   # Falls back to active provider in DB
    model: str | None = None      # Falls back to provider's active_model in DB

    @field_validator("model", mode="before")
    @classmethod
    def _coerce_model(cls, v):
        """Ensure model is a plain string — reject objects / [object Object] artifacts."""
        if v is None:
            return None
        if not isinstance(v, str):
            return None  # let the backend fall back to default
        # Reject JS-style [object Object] strings
        if "[object" in v:
            return None
        return v.strip() or None


class ApprovalRequest(BaseModel):
    session_id: str
    approval_id: str
    approved: bool


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/chat
# ─────────────────────────────────────────────────────────────────────────────

@router.post("")
async def chat(body: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Starts an agent turn for the given session.

    1. Validates the session exists
    2. Resolves the AI provider + API key
    3. Loads full conversation history
    4. Persists the user message
    5. Returns a StreamingResponse (SSE) that drives the agent loop

    The SSE stream is driven by run_agent_stream() in services/agent.py.
    The assistant message is persisted to the DB after the stream ends.
    """
    # ── 1. Validate session ───────────────────────────────────────────────
    session_result = await db.execute(select(Session).where(Session.id == body.session_id))
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{body.session_id}' not found.")

    # ── 2. Resolve provider ───────────────────────────────────────────────
    settings = get_settings()

    # ── 2a. Ensure tool registry is loaded ─────────────────────────────────
    # If the bridge wasn't available at startup (e.g. Revit started later),
    # trigger a lazy re-discovery now so the model receives tool schemas.
    if not registry.schemas:
        await registry.ensure_loaded()

    provider_name, model, api_key = await _resolve_provider(body, db, settings)

    try:
        provider = get_provider(provider_name, api_key=api_key, model=model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── 3. Load conversation history ──────────────────────────────────────
    msgs_result = await db.execute(
        select(Message)
        .where(Message.session_id == body.session_id)
        .order_by(Message.created_at.asc())
    )
    db_messages = msgs_result.scalars().all()
    history = _db_messages_to_history(db_messages)

    # ── 4. Persist user message ───────────────────────────────────────────
    user_msg = Message(
        id=str(uuid.uuid4()),
        session_id=body.session_id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    session.updated_at = datetime.now(timezone.utc)

    # We need to commit before streaming so the user message is durable
    await db.commit()

    history.append({"role": "user", "content": body.message})

    # ── 5. Stream ─────────────────────────────────────────────────────────
    message_id = str(uuid.uuid4())
    gate = create_gate(body.session_id)
    session_id = body.session_id

    async def event_generator():
        # Accumulate assistant content and tool calls for DB persistence
        accumulated_text: list[str] = []
        tc_map: dict[str, dict] = {}  # id -> {id, name, args, status, result, approved}
        accumulated_thoughts: list[str] = []

        try:
            async for chunk in run_agent_stream(
                provider=provider,
                messages=history,
                session_id=session_id,
                message_id=message_id,
                gate=gate,
            ):
                # Intercept events to accumulate assistant message data
                if chunk.startswith("data: "):
                    try:
                        payload = json.loads(chunk[6:].strip())
                        evt_type = payload.get("type")
                        if evt_type == "text_delta":
                            accumulated_text.append(payload.get("content", ""))
                        elif evt_type == "tool_call_pending":
                            tc_id = payload.get("id", "")
                            tc_map[tc_id] = {
                                "id": tc_id,
                                "name": payload.get("tool", ""),
                                "args": payload.get("args", {}),
                                "status": "pending",
                            }
                        elif evt_type == "tool_call_executing":
                            tc_id = payload.get("id", "")
                            if tc_id in tc_map:
                                tc_map[tc_id]["status"] = "executing"
                        elif evt_type == "tool_result":
                            tc_id = payload.get("id", "")
                            if tc_id in tc_map:
                                approved = payload.get("approved")
                                tc_map[tc_id]["status"] = "done" if approved else "rejected"
                                tc_map[tc_id]["result"] = payload.get("result")
                                tc_map[tc_id]["approved"] = approved
                        elif evt_type == "agent_thought":
                            accumulated_thoughts.append(payload.get("content", ""))
                    except (json.JSONDecodeError, AttributeError):
                        pass

                yield chunk
        except Exception as exc:
            logger.exception("Unhandled error in agent stream")
            yield sse.error("Internal agent error.", detail=str(exc))
            yield sse.done(session_id=session_id, message_id=message_id)
        finally:
            remove_gate(session_id)

            # ── Persist assistant message to DB ────────────────────────────
            # Use a fresh DB session since the request-scoped one may be closed
            full_text = "".join(accumulated_text).strip()
            # Note: services/agent.py's streaming buffer already filters out "[object Object]"
            # from text_delta chunks on emission, so no additional sanitization is needed here.
            accumulated_tool_calls = list(tc_map.values())
            if full_text or accumulated_tool_calls:
                try:
                    async with AsyncSessionLocal() as save_db:
                        assistant_message = Message(
                            id=message_id,
                            session_id=session_id,
                            role="assistant",
                            content=full_text,
                            tool_calls=(
                                json.dumps(accumulated_tool_calls)
                                if accumulated_tool_calls else None
                            ),
                            agent_thoughts=(
                                json.dumps(accumulated_thoughts)
                                if accumulated_thoughts else None
                            ),
                        )
                        save_db.add(assistant_message)

                        # Persist tool result messages so the model sees results on reload.
                        # tool_call_id is stored explicitly so _db_messages_to_history()
                        # can do a direct ID lookup instead of fragile positional indexing.
                        for tc in accumulated_tool_calls:
                            tc_id   = tc.get("id", "")
                            tc_name = tc.get("name", "unknown")
                            tc_result = tc.get("result")
                            result_content = json.dumps(tc_result) if tc_result is not None else "{}"
                            tool_msg = Message(
                                id=str(uuid.uuid4()),
                                session_id=session_id,
                                role="tool",
                                content=result_content,
                                tool_name=tc_name,
                                tool_call_id=tc_id,
                            )
                            save_db.add(tool_msg)

                        # Update session timestamp
                        sess_result = await save_db.execute(
                            select(Session).where(Session.id == session_id)
                        )
                        sess = sess_result.scalar_one_or_none()
                        if sess:
                            sess.updated_at = datetime.now(timezone.utc)

                        await save_db.commit()
                        logger.debug(
                            "Persisted assistant message %s + %d tool results for session %s",
                            message_id, len(accumulated_tool_calls), session_id,
                        )
                except Exception as save_exc:
                    logger.error(
                        "Failed to persist assistant message: %s", save_exc,
                        exc_info=True,
                    )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/chat/approve
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/approve")
async def approve_tool_call(body: ApprovalRequest):
    """
    Unblocks the agent that is paused waiting for approval.

    The agent stream for body.session_id must currently be paused (i.e. an
    active gate exists for this session). Returns immediately; the agent
    resumes asynchronously.
    """
    gate = get_gate(body.session_id)
    if gate is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"No agent is currently paused for session '{body.session_id}'. "
                "The stream may have already completed or timed out."
            ),
        )

    if gate.pending_tool_id != body.approval_id:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Approval ID mismatch. Expected '{gate.pending_tool_id}', "
                f"got '{body.approval_id}'."
            ),
        )

    gate.decide(approved=body.approved)
    return {"status": "ok", "approved": body.approved}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_provider(
    body: ChatRequest,
    db: AsyncSession,
    settings,
) -> tuple[str, str, str]:
    """
    Returns (provider_name, model, api_key).

    Priority order:
      1. Explicit values from the request body
      2. Active provider in the DB
      3. Default from config.py (env vars)
    """
    # Try DB active provider first
    result = await db.execute(
        select(ProviderConfig).where(ProviderConfig.active == True)  # noqa: E712
    )
    active_cfg = result.scalar_one_or_none()

    provider_name = body.provider or (active_cfg.provider if active_cfg else settings.default_provider)
    model = body.model or (active_cfg.active_model if active_cfg else settings.default_model) or settings.default_model

    # Guard against model being invalid (object, [object Object], empty, etc.)
    if not isinstance(model, str) or "[object" in model or not model.strip():
        model = settings.default_model
    model = model.strip()

    # Validate model against provider's known model list — resets stale/decommissioned models
    try:
        from providers import list_providers
        known = {p["name"]: p["models"] for p in list_providers()}
        provider_models = known.get(provider_name, [])
        if provider_models and model not in provider_models and model != settings.default_model:
            logger.warning(
                "Model '%s' not in %s model list — falling back to provider default.",
                model, provider_name,
            )
            model = provider_models[0]
    except Exception:
        pass  # Non-critical — let the provider handle unknown models

    # Resolve API key: DB record > env var
    result2 = await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider == provider_name)
    )
    cfg = result2.scalar_one_or_none()
    db_key = cfg.api_key if cfg else None
    env_key = getattr(settings, f"{provider_name}_api_key", "")
    api_key = db_key or env_key

    if not api_key:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No API key configured for provider '{provider_name}'. "
                "Please set it in Settings or your .env file."
            ),
        )

    return provider_name, model, api_key


def _db_messages_to_history(db_messages: list[Message]) -> list[dict]:
    """
    Convert persisted Message ORM objects to provider-agnostic history dicts.

    Tool-result messages are linked to their originating tool call via the
    stored `tool_call_id` column (direct ID lookup). For legacy rows written
    before this column existed the code falls back to positional indexing so
    old sessions continue to work correctly.
    """
    # Build a lookup: tool_call_id -> {id, name, args} from all assistant messages.
    # Used by the direct-lookup path for tool-result messages.
    tc_lookup: dict[str, dict] = {}
    for msg in db_messages:
        if msg.role == "assistant" and msg.tool_calls:
            try:
                for tc in json.loads(msg.tool_calls):
                    tc_id = tc.get("id", "")
                    if tc_id:
                        tc_lookup[tc_id] = tc
            except json.JSONDecodeError:
                pass

    # Positional fallback state (for legacy rows without tool_call_id)
    pending_tc_list: list[dict] = []
    tool_result_idx = 0

    history = []
    for msg in db_messages:
        entry: dict = {"role": msg.role, "content": msg.content}

        if msg.tool_calls:
            try:
                tcs = json.loads(msg.tool_calls)
                # Normalise: ensure args are dicts, not JSON strings
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

        if msg.role == "tool":
            # Prefer stored tool_name (always written since the initial implementation)
            if msg.tool_name:
                entry["name"] = msg.tool_name

            # ── Direct ID lookup (preferred — works for all rows written after the
            #    tool_call_id migration) ───────────────────────────────────────────
            if msg.tool_call_id and msg.tool_call_id in tc_lookup:
                entry["tool_call_id"] = msg.tool_call_id
                if not entry.get("name"):
                    entry["name"] = tc_lookup[msg.tool_call_id].get("name", "unknown")

            # ── Positional fallback (legacy rows without tool_call_id) ─────────────
            elif pending_tc_list and tool_result_idx < len(pending_tc_list):
                legacy_tc = pending_tc_list[tool_result_idx]
                if not entry.get("name"):
                    entry["name"] = legacy_tc.get("name", "unknown")
                if not entry.get("tool_call_id"):
                    entry["tool_call_id"] = legacy_tc.get("id", "")
                tool_result_idx += 1

        history.append(entry)
    return history
