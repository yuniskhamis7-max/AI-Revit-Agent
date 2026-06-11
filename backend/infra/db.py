# -*- coding: utf-8 -*-
"""
Database — Async SQLite client using raw SQL via aiosqlite.

Encapsulates all schema initialization and data persistence operations.
"""
from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timezone
import aiosqlite

logger = logging.getLogger(__name__)

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _uuid() -> str:
    return str(uuid.uuid4())

class Database:
    """
    Unified SQLite database client.
    Handles all queries and connection lifecycles.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize(self) -> None:
        """Create tables if they do not exist and ensure foreign keys are enabled."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            
            # 1. Sessions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)

            # 2. Messages table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT,
                    agent_thoughts TEXT,
                    tool_name TEXT,
                    tool_call_id TEXT,
                    approved INTEGER, -- 0 for false, 1 for true, null for none
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                );
            """)

            # 3. Provider configs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS provider_configs (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL UNIQUE,
                    api_key TEXT,
                    active_model TEXT,
                    active INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
            """)

            # 4. App settings table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            await db.commit()
        logger.info("SQLite database tables initialized successfully.")

    # ─────────────────────────────────────────────────────────────────────────
    # SESSIONS
    # ─────────────────────────────────────────────────────────────────────────

    async def list_sessions(self) -> list[dict]:
        """List all sessions ordered by updated_at desc."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions ORDER BY updated_at DESC;") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_session(self, name: str) -> dict:
        """Create a new chat session."""
        now = _now_iso()
        sid = _uuid()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO sessions (id, name, created_at, updated_at) VALUES (?, ?, ?, ?);",
                (sid, name, now, now)
            )
            await db.commit()
        return {"id": sid, "name": name, "created_at": now, "updated_at": now}

    async def get_session(self, session_id: str) -> dict | None:
        """Get session details by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM sessions WHERE id = ?;", (session_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def rename_session(self, session_id: str, new_name: str) -> dict | None:
        """Rename a session and refresh its updated_at timestamp."""
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "UPDATE sessions SET name = ?, updated_at = ? WHERE id = ?;",
                (new_name, now, session_id)
            ) as cursor:
                if cursor.rowcount == 0:
                    return None
            await db.commit()
        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session (cascades to delete all messages)."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("DELETE FROM sessions WHERE id = ?;", (session_id,)) as cursor:
                affected = cursor.rowcount
            await db.commit()
            return affected > 0

    # ─────────────────────────────────────────────────────────────────────────
    # MESSAGES
    # ─────────────────────────────────────────────────────────────────────────

    async def get_session_messages(self, session_id: str) -> list[dict]:
        """Fetch all messages for a session ordered by created_at asc."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC;",
                (session_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                # Helper: normalise approved boolean (0/1 -> False/True)
                res = []
                for row in rows:
                    d = dict(row)
                    if d["approved"] is not None:
                        d["approved"] = bool(d["approved"])
                    res.append(d)
                return res

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: str | None = None,
        agent_thoughts: str | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
        approved: bool | None = None,
        message_id: str | None = None
    ) -> dict:
        """Save a new message and refresh the session's updated_at timestamp."""
        now = _now_iso()
        mid = message_id or _uuid()
        approved_int = None if approved is None else (1 if approved else 0)

        async with aiosqlite.connect(self.db_path) as db:
            # 1. Insert message
            await db.execute(
                """
                INSERT INTO messages (
                    id, session_id, role, content, tool_calls, agent_thoughts, tool_name, tool_call_id, approved, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (mid, session_id, role, content, tool_calls, agent_thoughts, tool_name, tool_call_id, approved_int, now)
            )
            # 2. Update session updated_at
            await db.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?;",
                (now, session_id)
            )
            await db.commit()

        return {
            "id": mid,
            "session_id": session_id,
            "role": role,
            "content": content,
            "tool_calls": tool_calls,
            "agent_thoughts": agent_thoughts,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "approved": approved,
            "created_at": now
        }

    # ─────────────────────────────────────────────────────────────────────────
    # PROVIDER CONFIGS
    # ─────────────────────────────────────────────────────────────────────────

    async def get_active_provider(self) -> dict | None:
        """Get the active provider configuration."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM provider_configs WHERE active = 1;") as cursor:
                row = await cursor.fetchone()
                if row:
                    d = dict(row)
                    d["active"] = bool(d["active"])
                    return d
                return None

    async def get_provider_config(self, provider: str) -> dict | None:
        """Get provider config details."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM provider_configs WHERE provider = ?;", (provider,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    d = dict(row)
                    d["active"] = bool(d["active"])
                    return d
                return None

    async def list_provider_configs(self) -> list[dict]:
        """List all provider configurations."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM provider_configs;") as cursor:
                rows = await cursor.fetchall()
                res = []
                for row in rows:
                    d = dict(row)
                    d["active"] = bool(d["active"])
                    res.append(d)
                return res

    async def save_provider_config(
        self, provider: str, api_key: str, active_model: str, active: bool
    ) -> None:
        """Upsert provider configuration and manage active status constraints."""
        now = _now_iso()
        active_val = 1 if active else 0
        async with aiosqlite.connect(self.db_path) as db:
            # If setting this provider active, set all others inactive
            if active_val == 1:
                await db.execute("UPDATE provider_configs SET active = 0;")
            
            await db.execute(
                """
                INSERT INTO provider_configs (id, provider, api_key, active_model, active, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    api_key = excluded.api_key,
                    active_model = excluded.active_model,
                    active = excluded.active,
                    updated_at = excluded.updated_at;
                """,
                (_uuid(), provider, api_key, active_model, active_val, now)
            )
            await db.commit()

    # ─────────────────────────────────────────────────────────────────────────
    # APP SETTINGS
    # ─────────────────────────────────────────────────────────────────────────

    async def get_all_settings(self) -> dict[str, str]:
        """Fetch all app settings as a flat dictionary."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT key, value FROM app_settings;") as cursor:
                rows = await cursor.fetchall()
                return {row["key"]: row["value"] for row in rows}

    async def upsert_settings(self, settings_dict: dict[str, str]) -> None:
        """Bulk insert or update application settings."""
        now = _now_iso()
        async with aiosqlite.connect(self.db_path) as db:
            for key, value in settings_dict.items():
                await db.execute(
                    """
                    INSERT INTO app_settings (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at;
                    """,
                    (key, value, now)
                )
            await db.commit()
