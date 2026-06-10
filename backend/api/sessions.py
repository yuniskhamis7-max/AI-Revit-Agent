# -*- coding: utf-8 -*-
"""
Sessions API — CRUD routes for free-form named chat sessions.

Routes:
  GET    /api/sessions            — list all sessions (newest first)
  POST   /api/sessions            — create a new session
  GET    /api/sessions/{id}       — get session detail + messages
  PATCH  /api/sessions/{id}       — rename a session
  DELETE /api/sessions/{id}       — delete session + all messages
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Message, Session

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    """
    Request body for creating a new chat session.

    Attributes:
        name: Human-readable name for the session (e.g. 'Grid Layout Task').
    """
    name: str


class SessionPatch(BaseModel):
    """
    Request body for renaming an existing session.

    Attributes:
        name: New human-readable name to assign to the session.
    """
    name: str


class MessageOut(BaseModel):
    """
    Serialised message returned in API responses.

    Attributes:
        id:             Unique UUID of the message.
        role:           Message role — 'user', 'assistant', or 'tool'.
        content:        Text content of the message. For tool messages, this is
                        the JSON-serialised tool result.
        tool_calls:     JSON string of tool call list (assistant messages only).
                        Each entry contains {id, name, args, status, result}.
        agent_thoughts: JSON string of agent thought list (assistant messages only).
                        Synthetic step-by-step status messages from the orchestrator.
        tool_name:      Name of the tool that produced this result (tool messages only).
        approved:       Approval decision for action tool calls.
                        None for fetch tools, True/False for action tools.
        created_at:     UTC timestamp when the message was persisted.
    """
    id: str
    role: str
    content: str
    tool_calls: str | None = None
    agent_thoughts: str | None = None
    tool_name: str | None = None
    approved: bool | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    """
    Serialised session summary returned in list/create/update responses.

    Attributes:
        id:         Unique UUID of the session.
        name:       Human-readable session name.
        created_at: UTC timestamp when the session was created.
        updated_at: UTC timestamp of the last activity in this session.
    """
    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionDetailOut(SessionOut):
    """
    Extended session response that includes the full message history.

    Attributes:
        messages: Ordered list of all messages in the session (oldest first).
    """
    messages: list[MessageOut] = []


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """
    List all chat sessions ordered by most recently updated first.

    Returns:
        list[SessionOut]: All sessions with id, name, and timestamps.
    """
    result = await db.execute(
        select(Session).order_by(Session.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new empty chat session with the given name.

    Args:
        body: Request body containing the session name.
        db:   Injected async database session.

    Returns:
        SessionOut: The newly created session with generated UUID and timestamps.
    """
    session = Session(id=str(uuid.uuid4()), name=body.name)
    db.add(session)
    await db.flush()
    return session


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a single session with its full message history.

    Args:
        session_id: UUID of the session to retrieve.
        db:         Injected async database session.

    Returns:
        SessionDetailOut: Session metadata plus all messages ordered by created_at.

    Raises:
        HTTPException(404): If no session with the given ID exists.
    """
    session = await _get_or_404(session_id, db)
    return session


@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: str, body: SessionPatch, db: AsyncSession = Depends(get_db)
):
    """
    Rename an existing session.

    Args:
        session_id: UUID of the session to rename.
        body:       Request body containing the new name.
        db:         Injected async database session.

    Returns:
        SessionOut: Updated session with the new name and refreshed updated_at.

    Raises:
        HTTPException(404): If no session with the given ID exists.
    """
    session = await _get_or_404(session_id, db)
    session.name = body.name
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """
    Delete a session and all its associated messages (cascade).

    Args:
        session_id: UUID of the session to delete.
        db:         Injected async database session.

    Returns:
        204 No Content on success.

    Raises:
        HTTPException(404): If no session with the given ID exists.
    """
    session = await _get_or_404(session_id, db)
    await db.delete(session)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_404(session_id: str, db: AsyncSession) -> Session:
    """
    Fetch a session by ID or raise a 404 HTTPException.

    Args:
        session_id: UUID of the session to look up.
        db:         Injected async database session.

    Returns:
        Session: The matching ORM session object.

    Raises:
        HTTPException(404): If no session with the given ID exists.
    """
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session
