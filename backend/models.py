# -*- coding: utf-8 -*-
"""
ORM Models — SQLAlchemy 2.0 mapped dataclasses for all persistent entities.

Tables:
  sessions        — free-form named chat sessions
  messages        — full message history per session
  provider_configs— per-provider API keys and active flag
  app_settings    — key/value store for app-level configuration
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Session
# ─────────────────────────────────────────────────────────────────────────────

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # Relationships
    messages: Mapped[list[Message]] = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Message
# ─────────────────────────────────────────────────────────────────────────────

class Message(Base):
    """
    Stores every turn in a conversation.

    role values:
      'user'        — human input
      'assistant'   — model text output
      'tool_result' — observation returned to the model after tool execution

    tool_calls is a JSON string: list of {id, name, args, requires_approval}
    approved is only meaningful for action tool calls:
      None  → fetch tool (no approval needed)
      True  → user approved
      False → user rejected
    """
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_calls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_thoughts: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    approved: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # Relationships
    session: Mapped[Session] = relationship("Session", back_populates="messages")


# ─────────────────────────────────────────────────────────────────────────────
# ProviderConfig
# ─────────────────────────────────────────────────────────────────────────────

class ProviderConfig(Base):
    """
    Stores per-provider configuration: API key and whether this provider
    is currently active. Only one provider should have active=True at a time,
    but the constraint is soft (enforced at the service layer).

    provider values: 'gemini' | 'openai' | 'anthropic'
    """
    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


# ─────────────────────────────────────────────────────────────────────────────
# AppSetting
# ─────────────────────────────────────────────────────────────────────────────

class AppSetting(Base):
    """
    Simple key/value configuration store for app-level settings
    that the frontend can read and write (e.g. theme, sidebar width).
    """
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
