# -*- coding: utf-8 -*-
"""
FastAPI Application — Entry point for the AI-Revit Agent backend.
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
from infra.db import Database
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

    # 1. Ensure the data/ directory exists and initialize SQLite DB
    db_file = Path(__file__).parent / settings.database_path
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    db = Database(str(db_file))
    await db.initialize()
    app.state.db = db
    logger.info("SQLite database tables initialized and ready.")

    # 2. Initialise shared HTTP client (for Revit bridge calls)
    init_http_client()

    # 3. Discover Revit tools
    try:
        schemas = await discover_tools()
        registry.load(schemas)
        if schemas:
            logger.info("Tool registry loaded: %d tools.", len(schemas))
        else:
            logger.warning(
                "Tool registry is empty. Start Revit and click 'Start Bridge'."
            )
    except Exception as exc:
        logger.warning(
            "Initial Revit tool discovery failed (Revit may not be running): %s. "
            "The backend will start normally, and Revit tools will be automatically loaded "
            "when Revit bridge comes online.",
            exc
        )

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
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=settings.development_mode,
        log_level=settings.log_level.lower(),
    )
