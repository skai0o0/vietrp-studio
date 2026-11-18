"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import include_routers
from app.core.config import Settings, get_settings
from app.core.db import dispose_engine
from app.core.errors import AppError, register_error_handlers
from app.llm.deps import build_llm_services


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # One shared OpenRouter client, pricing cache and correction table for the whole process.
    # Tests may pre-set `app.state.llm_services` (e.g. over a RecordedLLM transport); keep theirs.
    if getattr(app.state, "llm_services", None) is None:
        app.state.llm_services = build_llm_services(app.state.settings)
    try:
        yield
    finally:
        await app.state.llm_services.aclose()
        await dispose_engine()


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built SPA: real files first, `index.html` for any other non-API path."""
    index = dist / "index.html"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        if full_path == "api" or full_path.startswith("api/"):
            raise AppError("not_found", "Not found", 404)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="VietRP Studio", version=__version__, lifespan=_lifespan)
    app.state.settings = settings
    register_error_handlers(app)

    if settings.env == "dev":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    include_routers(app)

    dist = settings.frontend_dist_path
    if (dist / "index.html").is_file():
        _mount_frontend(app, dist)
    return app


def __getattr__(name: str) -> FastAPI:
    """Lazy module-level `app` so `uvicorn app.main:app` works while importing this module needs no env."""
    if name == "app":
        return create_app()
    raise AttributeError(name)
