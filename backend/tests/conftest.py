from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app

# Dummy values for tests only; not real keys.
DUMMY_PEPPER = "p" * 40
DUMMY_SESSION_SECRET = "s" * 40
DUMMY_DATABASE_URL = "postgresql+asyncpg://user:pw@127.0.0.1:5432/dummy"
NO_FRONTEND_DIST = Path("tests/__no_frontend_dist__")


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": DUMMY_DATABASE_URL,
        "server_pepper": DUMMY_PEPPER,
        "session_secret": DUMMY_SESSION_SECRET,
        # Tests must not depend on whether the frontend has been built on this machine.
        "frontend_dist_dir": NO_FRONTEND_DIST,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
