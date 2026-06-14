# -*- coding: utf-8 -*-
"""
Backend Configuration — Settings loaded from .env / environment variables.

DEVELOPMENT_MODE toggle:
  True  → open CORS, DEBUG logging, bridge soft-fail
  False → restricted CORS, INFO logging, hard bridge errors
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application-wide configuration loaded from .env and environment variables.

    All settings are validated and typed via Pydantic. The .env file is read
    from the backend/ directory. Unknown environment variables are silently
    ignored (extra="ignore").

    Attributes:
        development_mode: Master toggle for developer ergonomics. When True,
            CORS is open, logging is DEBUG, and bridge failures are soft.
            Set to False for production deployments.
        gemini_api_key:   API key for Google Gemini provider.
        default_provider: Fallback provider name when none is persisted in DB.
        default_model:    Fallback model ID when none is persisted in DB.
        agent_max_turns:  Maximum number of agent loop iterations per user turn.
            Prevents infinite loops on complex multi-step automations.
        revit_bridge_host: Hostname/IP of the C# Revit bridge server.
        revit_bridge_port: TCP port the Revit bridge listens on.
        backend_host:     Host address the FastAPI backend binds to.
        backend_port:     TCP port the FastAPI backend listens on.
        database_path:    Relative path (from backend/) to the SQLite database file.
    """

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Development ──────────────────────────────────────────────────────────
    development_mode: bool = True
    """
    Master toggle for developer ergonomics.
    Set to False for production / demo deployments.
    """

    use_multi_agent: bool = True
    """
    Toggle to switch between multi-agent pipeline and single-agent loop.
    Defaults to True.
    """

    # ── AI Provider Keys ─────────────────────────────────────────────────────
    gemini_api_key: str = ""
    """Google Gemini API key. Empty string means not configured via env."""

    # Default provider + model used when none is persisted in the DB yet
    default_provider: str = "gemini"
    """Fallback provider name when no active provider is stored in the DB."""

    default_model: str = "gemini-2.5-flash"
    """Fallback model ID when no active model is stored in the DB."""

    # Maximum number of agent loop turns per conversation turn.
    # Increase for complex multi-step Revit automations, decrease for faster
    # responses in simple fetch-only workflows.
    agent_max_turns: int = 20
    """
    Maximum number of agent loop iterations per user turn.
    Prevents infinite loops on complex multi-step automations.
    """

    # ── Revit Bridge ─────────────────────────────────────────────────────────
    revit_bridge_host: str = "http://127.0.0.1"
    """Hostname or IP address of the C# Revit bridge HTTP server."""

    revit_bridge_port: int = 8080
    """TCP port the Revit bridge HTTP server listens on."""

    @property
    def revit_execute_url(self) -> str:
        """
        Full URL for the Revit bridge tool execution endpoint.

        Returns:
            str: e.g. 'http://127.0.0.1:8080/execute/'
        """
        return f"{self.revit_bridge_host}:{self.revit_bridge_port}/execute/"

    @property
    def revit_discovery_url(self) -> str:
        """
        Full URL for the Revit bridge tool discovery endpoint.

        Returns:
            str: e.g. 'http://127.0.0.1:8080/tools/'
        """
        return f"{self.revit_bridge_host}:{self.revit_bridge_port}/tools/"

    # ── Server ───────────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    """Host address the FastAPI backend binds to. '0.0.0.0' listens on all interfaces."""

    backend_port: int = 8000
    """TCP port the FastAPI backend listens on."""

    # ── Database ─────────────────────────────────────────────────────────────
    database_path: str = "data/agent.db"
    """Relative path (from backend/) to the SQLite database file."""

    # ── CORS ─────────────────────────────────────────────────────────────────
    @property
    def cors_origins(self) -> list[str]:
        """
        Allowed CORS origins based on development mode.

        Returns:
            list[str]: ['*'] in dev mode (allow all), or restricted to the
                backend's own origin in production.
        """
        if self.development_mode:
            return ["*"]
        return [f"http://localhost:{self.backend_port}"]

    # ── Logging ──────────────────────────────────────────────────────────────
    @property
    def log_level(self) -> str:
        """
        Logging verbosity level.

        Returns:
            str: 'DEBUG' in dev mode for verbose output, 'INFO' in production.
        """
        return "DEBUG" if self.development_mode else "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance."""
    return Settings()
