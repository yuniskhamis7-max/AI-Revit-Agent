# -*- coding: utf-8 -*-
"""
Database — Async SQLite engine and session factory via SQLAlchemy 2.0.

All tables are created automatically on first startup via the lifespan hook
in main.py. No migrations needed for local v1.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


def _build_engine():
    """
    Constructs the async SQLAlchemy engine using the configured database URL.

    The engine uses aiosqlite for non-blocking SQLite access. SQL query logging
    (echo) is enabled only in development mode for debugging. check_same_thread
    is disabled because SQLAlchemy manages thread safety via its connection pool.

    Returns:
        sqlalchemy.ext.asyncio.AsyncEngine: The configured async database engine.
    """
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.development_mode,   # SQL query logging in dev mode
        connect_args={"check_same_thread": False},
    )


# Module-level singletons — created once, reused across the app lifetime
engine = _build_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def create_all_tables() -> None:
    """Create all tables defined in models.py. Called from lifespan."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """
    FastAPI dependency that provides a scoped async DB session.

    Usage in route handlers:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
