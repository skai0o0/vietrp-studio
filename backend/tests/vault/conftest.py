from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.deps import SessionStoreDep, SettingsDep
from app.main import create_app
from app.services.vault_service import VaultService, get_vault_service
from tests.conftest import make_settings
from tests.vault.fakes import FakeSecretRepository, FakeVaultRepository

# Cheap Argon2 so the suite stays fast; the minimum Argon2 allows is memory >= 8 * parallelism KiB.
FAST_ARGON2 = {"argon2_time_cost": 1, "argon2_memory_cost_kib": 64, "argon2_parallelism": 1}


@pytest.fixture
def vault_settings() -> Settings:
    return make_settings(**FAST_ARGON2)


@pytest.fixture
def vault_repos() -> tuple[FakeVaultRepository, FakeSecretRepository]:
    return FakeVaultRepository(), FakeSecretRepository()


@pytest.fixture
def vault_app(vault_settings: Settings, vault_repos: tuple[FakeVaultRepository, FakeSecretRepository]) -> FastAPI:
    app = create_app(vault_settings)
    vaults, secrets_repo = vault_repos

    def override_service(store: SessionStoreDep, settings: SettingsDep) -> VaultService:
        return VaultService(vaults, secrets_repo, store, settings)

    app.dependency_overrides[get_settings] = lambda: vault_settings
    app.dependency_overrides[get_vault_service] = override_service
    return app


@pytest.fixture
async def vault_client(vault_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=vault_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
