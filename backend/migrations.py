# -*- coding: utf-8 -*-
"""
Idempotent database schema migrations for the AI-Revit Agent.
"""
from __future__ import annotations

import logging
from sqlalchemy import text, inspect as sa_inspect
from database import engine

logger = logging.getLogger(__name__)

async def run_startup_migrations() -> None:
    """
    Lightweight, idempotent schema migrations for columns added after the
    initial table creation. Each entry is a (table, column, sql_type) tuple.
    Add new columns here rather than creating separate migration functions.
    """
    pending: list[tuple[str, str, str]] = [
        ("messages", "agent_thoughts", "TEXT"),
        ("messages", "tool_call_id",   "TEXT"),
    ]

    async with engine.begin() as conn:
        for table, column, sql_type in pending:
            def _needs_column(sync_conn, t=table, c=column):
                insp = sa_inspect(sync_conn)
                cols = [col["name"] for col in insp.get_columns(t)]
                return c not in cols

            if await conn.run_sync(_needs_column):
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
                )
                logger.info("Migration: added column '%s' to table '%s'.", column, table)
