# -*- coding: utf-8 -*-
"""
Sessions API — CRUD routes for free-form named chat sessions.
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from infra.db import Database

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

# Dependency to get Database client from application state
def get_db(request: Request) -> Database:
    return request.app.state.db

# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[SessionOut])
async def list_sessions(db: Database = Depends(get_db)):
    """List all chat sessions ordered by most recently updated first."""
    return await db.list_sessions()

@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionCreate, db: Database = Depends(get_db)):
    """Create a new empty chat session."""
    return await db.create_session(body.name)

@router.get("/{session_id}", response_model=SessionDetailOut)
async def get_session(session_id: str, db: Database = Depends(get_db)):
    """Retrieve a single session with its full message history."""
    session = await db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    
    messages = await db.get_session_messages(session_id)
    return {
        "id": session["id"],
        "name": session["name"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "messages": messages
    }

@router.patch("/{session_id}", response_model=SessionOut)
async def rename_session(
    session_id: str, body: SessionPatch, db: Database = Depends(get_db)
):
    """Rename an existing session."""
    session = await db.rename_session(session_id, body.name)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session

@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: str, db: Database = Depends(get_db)):
    """Delete a session and all its associated messages."""
    deleted = await db.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
