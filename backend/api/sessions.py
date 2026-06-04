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
    name: str


class SessionPatch(BaseModel):
    name: str


class MessageOut(BaseModel):
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
    id: str
    name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionDetailOut(SessionOut):
    messages: list[MessageOut] = []


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).order_by(Session.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionCreate, db: AsyncSession = Depends(get_db)):
    session = Session(id=str(uuid.uuid4()), name=body.name)
    db.add(session)
    await db.flush()
    return session


@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await _get_or_404(session_id, db)
    return session


@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: str, body: SessionPatch, db: AsyncSession = Depends(get_db)
):
    session = await _get_or_404(session_id, db)
    session.name = body.name
    session.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await _get_or_404(session_id, db)
    await db.delete(session)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_or_404(session_id: str, db: AsyncSession) -> Session:
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session
