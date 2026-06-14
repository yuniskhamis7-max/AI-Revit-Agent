# -*- coding: utf-8 -*-
"""
Sessions API — CRUD routes for free-form named chat sessions.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
    images: list[str] | None = None

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


@router.get("/{session_id}/export")
async def export_session(
    session_id: str,
    format: str = "markdown",
    db: Database = Depends(get_db)
):
    """
    Export the session's user and assistant message history to a file.
    Supports 'markdown' (default) and 'json' formats.
    """
    session = await db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    messages = await db.get_session_messages(session_id)
    
    # Filter out internal 'tool' messages for the export file
    display_messages = [m for m in messages if m["role"] in ("user", "assistant")]

    if format.lower() == "json":
        export_messages = []
        for m in display_messages:
            msg_dict = {
                "role": m["role"],
                "content": m["content"],
                "created_at": m["created_at"]
            }
            if m.get("agent_thoughts"):
                try:
                    msg_dict["agent_thoughts"] = json.loads(m["agent_thoughts"])
                except Exception:
                    msg_dict["agent_thoughts"] = m["agent_thoughts"]
            if m.get("tool_calls"):
                try:
                    msg_dict["tool_calls"] = json.loads(m["tool_calls"])
                except Exception:
                    msg_dict["tool_calls"] = m["tool_calls"]
            export_messages.append(msg_dict)

        export_data = {
            "session_id": session["id"],
            "session_name": session["name"],
            "created_at": session["created_at"],
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "messages": export_messages
        }
        content = json.dumps(export_data, indent=2)
        media_type = "application/json"
        filename = f"{session['name'].replace(' ', '_')}_export.json"
    else:
        # Markdown export
        lines = [
            f"# Session: {session['name']}",
            f"Exported at: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            "---",
            ""
        ]
        for m in display_messages:
            role_label = "User" if m["role"] == "user" else "Assistant"
            try:
                # Format timestamp nicely
                dt = datetime.fromisoformat(m["created_at"])
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
            except Exception:
                time_str = m["created_at"]

            lines.append(f"## {role_label} ({time_str})")

            # Show agent activity if present
            if m.get("agent_thoughts"):
                try:
                    thoughts = json.loads(m["agent_thoughts"])
                    if thoughts:
                        lines.append("### Agent Activity:")
                        for thought in thoughts:
                            lines.append(f"- {thought}")
                        lines.append("")
                except Exception:
                    pass

            # Show main text content
            if m["content"]:
                lines.append(m["content"])
                lines.append("")

            # Format tool executions if present (assistant messages)
            if m["role"] == "assistant" and m.get("tool_calls"):
                try:
                    tcs = json.loads(m["tool_calls"])
                    if tcs:
                        for tc in tcs:
                            lines.append(f"### Tool Call: `{tc.get('name')}`")
                            status = tc.get("status", "unknown")
                            lines.append(f"- **Status**: {status}")

                            args = tc.get("args")
                            if args:
                                lines.append("- **Arguments**:")
                                lines.append("  ```json")
                                args_str = json.dumps(args, indent=2)
                                for arg_line in args_str.splitlines():
                                    lines.append(f"  {arg_line}")
                                lines.append("  ```")

                            result = tc.get("result")
                            if result is not None:
                                lines.append("- **Response**:")
                                lines.append("  ```json")
                                result_str = json.dumps(result, indent=2)
                                for res_line in result_str.splitlines():
                                    lines.append(f"  {res_line}")
                                lines.append("  ```")
                            lines.append("")
                except Exception:
                    pass

        content = "\n".join(lines)
        media_type = "text/markdown"
        filename = f"{session['name'].replace(' ', '_')}_export.md"

    # Add content-disposition header to trigger native file download
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Access-Control-Expose-Headers": "Content-Disposition"
    }

    return Response(content=content, media_type=media_type, headers=headers)
