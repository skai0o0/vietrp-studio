"""The vault flow against real PostgreSQL. Skipped unless VIETRP_TEST_DATABASE_URL is set."""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.main import create_app
from app.models import Base
from app.models.vault import Vault
from tests.conftest import make_settings
from tests.vault.conftest import FAST_ARGON2
from tests.vault.flow import run_vault_flow

TEST_DATABASE_URL = os.environ.get("VIETRP_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="VIETRP_TEST_DATABASE_URL is not set")


@pytest.fixture
async def pg_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    assert TEST_DATABASE_URL
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_flow_on_postgres(pg_sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    settings = make_settings(**FAST_ARGON2)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    async def db_session() -> AsyncIterator[AsyncSession]:
        async with pg_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = db_session
    passphrase = f"pg test {secrets.token_hex(8)} passphrase"
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await run_vault_flow(client, passphrase)
    finally:
        async with pg_sessionmaker() as session:
            await session.execute(delete(Vault).where(Vault.display_name == "Nem 2"))
            await session.commit()
