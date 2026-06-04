# -*- coding: utf-8 -*-
"""
FastAPI Application — Entry point for the AI-Revit Agent backend.

Startup sequence:
  1. Ensure data/ directory exists
  2. Create SQLite tables (idempotent) + run column migrations
  3. Initialise shared HTTP client
  4. Discover Revit tools from bridge (soft-fail in DEVELOPMENT_MODE)
  5. Load tool registry
  6. Mount API routers
  7. Serve React SPA from frontend/dist/ (if built)

Run in development:
  uvicorn main:app --reload --port 8000

Run in production:
  uvicorn main:app --port 8000
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.chat import router as chat_router
from api.providers import router as providers_router
from api.sessions import router as sessions_router
from api.settings import router as settings_router
from config import get_settings
from database import create_all_tables
from migrations import run_startup_migrations
from services.revit_bridge import discover_tools, init_http_client, close_http_client
from services.tool_registry import registry

# ─────────────────────────────────────────────────────────────────────────────
# Logging setup
# ─────────────────────────────────────────────────────────────────────────────

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)

# Startup schema migrations are managed in backend/migrations.py


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown logic."""
    logger.info("=" * 60)
    logger.info("  AI-Revit Agent Backend — Starting up")
    logger.info("  DEVELOPMENT_MODE = %s", settings.development_mode)
    logger.info("=" * 60)

    # 1. Ensure the data/ directory exists before touching the DB
    db_file = Path(__file__).parent / settings.database_path
    db_file.parent.mkdir(parents=True, exist_ok=True)

    # 2. Initialise database tables and run column migrations
    await create_all_tables()
    await run_startup_migrations()
    logger.info("Database tables ready.")

    # 3. Initialise shared HTTP client (for Revit bridge calls)
    init_http_client()

    # 4. Discover Revit tools
    try:
        schemas = await discover_tools()
        registry.load(schemas)
        if schemas:
            logger.info("Tool registry loaded: %d tools.", len(schemas))
        else:
            logger.warning(
                "Tool registry is empty. Start Revit and click 'Start Bridge', "
                "then restart the backend."
            )
    except Exception as exc:
        logger.error("Tool discovery failed: %s", exc)
        if not settings.development_mode:
            raise

    logger.info("Backend ready. Listening on http://%s:%d", settings.backend_host, settings.backend_port)

    yield  # ← application runs here

    logger.info("Backend shutting down.")
    await close_http_client()


# ─────────────────────────────────────────────────────────────────────────────
# App factory
# ─────────────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-Revit Agent",
        description="AI-assisted Revit automation platform API",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── API routers ───────────────────────────────────────────────────────────
    app.include_router(chat_router)
    app.include_router(sessions_router)
    app.include_router(providers_router)
    app.include_router(settings_router)

    # ── Serve React SPA (production mode) ────────────────────────────────────
    # The frontend/dist directory is created by `npm run build` in frontend/.
    # In development, use `npm run dev` (Vite dev server on :5173 with /api proxy).
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        # Mount the assets directory so JS/CSS files are served correctly
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

        # Catch-all for SPA routing — serve index.html for all non-API paths
        from fastapi.responses import FileResponse

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            index = frontend_dist / "index.html"
            if index.exists():
                return FileResponse(index)
            return {"detail": "Frontend not built. Run `npm run build` in frontend/."}

        logger.info("Serving React SPA from %s", frontend_dist)
    else:
        logger.info(
            "Frontend dist not found at %s. "
            "Run `npm run build` in frontend/ for production serving, "
            "or use `npm run dev` for development.",
            frontend_dist,
        )

    return app


app = create_app()


# ─────────────────────────────────────────────────────────────────────────────
# Dev entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.development_mode,
        log_level=settings.log_level.lower(),
    )
