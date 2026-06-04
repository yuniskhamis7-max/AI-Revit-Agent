# -*- coding: utf-8 -*-
"""
Backend Configuration — Settings loaded from .env / environment variables.

DEVELOPMENT_MODE toggle:
  True  → auto-approve tools, open CORS, DEBUG logging, bridge soft-fail
  False → approval gate enforced, restricted CORS, INFO logging, hard bridge errors
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    # ── AI Provider Keys ─────────────────────────────────────────────────────
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    groq_api_key: str = ""
    openrouter_api_key: str = ""

    # Default provider + model used when none is persisted in the DB yet
    default_provider: str = "gemini"
    default_model: str = "gemini-2.5-flash"

    # Maximum number of agent loop turns per conversation turn.
    # Increase for complex multi-step Revit automations, decrease for faster
    # responses in simple fetch-only workflows.
    agent_max_turns: int = 20

    # ── Revit Bridge ─────────────────────────────────────────────────────────
    revit_bridge_host: str = "http://127.0.0.1"
    revit_bridge_port: int = 8080

    @property
    def revit_execute_url(self) -> str:
        return f"{self.revit_bridge_host}:{self.revit_bridge_port}/execute/"

    @property
    def revit_discovery_url(self) -> str:
        return f"{self.revit_bridge_host}:{self.revit_bridge_port}/tools/"

    # ── Server ───────────────────────────────────────────────────────────────
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # ── Database ─────────────────────────────────────────────────────────────
    database_path: str = "data/agent.db"

    @property
    def database_url(self) -> str:
        db_file = Path(__file__).parent / self.database_path
        return f"sqlite+aiosqlite:///{db_file}"

    # ── CORS ─────────────────────────────────────────────────────────────────
    @property
    def cors_origins(self) -> list[str]:
        if self.development_mode:
            return ["*"]
        return [f"http://localhost:{self.backend_port}"]

    # ── Logging ──────────────────────────────────────────────────────────────
    @property
    def log_level(self) -> str:
        return "DEBUG" if self.development_mode else "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Returns a cached singleton Settings instance."""
    return Settings()
