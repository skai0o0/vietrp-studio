from __future__ import annotations

import os
import secrets
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.deps import SessionStoreDep, SettingsDep
from app.main import create_app
from app.models import Base
from app.models.library import LorebookLink
from app.models.vault import Vault
from app.services.asset_service import get_asset_repo
from app.services.library_service import get_repos
from app.services.vault_service import VaultService, get_vault_service
from tests.conftest import make_settings
from tests.library.fakes import FakeStore, make_fake_repos
from tests.vault.conftest import FAST_ARGON2
from tests.vault.fakes import FakeSecretRepository, FakeVaultRepository

TEST_DATABASE_URL = os.environ.get("VIETRP_TEST_DATABASE_URL")


@dataclass
class LibEnv:
    """Two unlocked vaults (A and B) on one app, backed by fakes or by real PostgreSQL."""

    app: FastAPI
    a: httpx.AsyncClient
    b: httpx.AsyncClient
    links_of: Callable[[str], Awaitable[set[str]]]


async def _new_vault(client: httpx.AsyncClient, name: str) -> None:
    passphrase = f"library test {secrets.token_hex(8)} passphrase"
    response = await client.post("/api/vault/create", json={"passphrase": passphrase, "display_name": name})
    assert response.status_code == 201, response.text


async def _make_clients(app: FastAPI, tag: str) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient]]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as a,
        httpx.AsyncClient(transport=transport, base_url="http://test") as b,
    ):
        await _new_vault(a, f"Alice {tag}")
        await _new_vault(b, f"Bob {tag}")
        yield a, b


def _settings() -> Settings:
    return make_settings(**FAST_ARGON2, unlock_rate_limit_attempts=10_000)


async def _fake_env() -> AsyncIterator[LibEnv]:
    settings = _settings()
    app = create_app(settings)
    vaults = FakeVaultRepository()
    store = FakeStore(vaults)
    repos = make_fake_repos(store)

    def vault_service(session_store: SessionStoreDep, current: SettingsDep) -> VaultService:
        return VaultService(vaults, FakeSecretRepository(), session_store, current)

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_vault_service] = vault_service
    app.dependency_overrides[get_repos] = lambda: repos
    app.dependency_overrides[get_asset_repo] = lambda: repos.assets

    async def links_of(target_id: str) -> set[str]:
        return {str(link[3]) for link in store.links if str(link[2]) == target_id}

    async for a, b in _make_clients(app, "fake"):
        yield LibEnv(app, a, b, links_of)


async def _pg_env() -> AsyncIterator[LibEnv]:
    assert TEST_DATABASE_URL
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    async def db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = db_session

    async def links_of(target_id: str) -> set[str]:
        async with sessionmaker() as session:
            rows = await session.scalars(
                select(LorebookLink.lorebook_id).where(LorebookLink.target_id == uuid.UUID(target_id))
            )
            return {str(r) for r in rows}

    tag = secrets.token_hex(4)
    try:
        async for a, b in _make_clients(app, tag):
            yield LibEnv(app, a, b, links_of)
    finally:
        async with sessionmaker() as session:
            await session.execute(delete(Vault).where(Vault.display_name.in_([f"Alice {tag}", f"Bob {tag}"])))
            await session.commit()
        await engine.dispose()


@pytest.fixture(params=["fake", "postgres"])
async def env(request: pytest.FixtureRequest) -> AsyncIterator[LibEnv]:
    if request.param == "postgres" and not TEST_DATABASE_URL:
        pytest.skip("VIETRP_TEST_DATABASE_URL is not set")
    factory = _fake_env if request.param == "fake" else _pg_env
    async for value in factory():
        yield value
