from __future__ import annotations

import logging

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.deps import SessionStoreDep, SettingsDep
from app.core.sessions import SessionStore
from app.main import create_app
from app.services.vault_service import VaultService, get_vault_service
from tests.conftest import make_settings
from tests.vault.fakes import FakeSecretRepository, FakeVaultRepository
from tests.vault.flow import SECRET_NAME, SECRET_VALUE, run_vault_flow

PASSPHRASE = "correct horse battery staple"


async def test_full_flow_with_fake_repositories(
    vault_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        await run_vault_flow(vault_client, PASSPHRASE, None)
    assert SECRET_VALUE not in caplog.text
    assert PASSPHRASE not in caplog.text


async def test_weak_passphrase_rejected(vault_client: httpx.AsyncClient) -> None:
    r = await vault_client.post("/api/vault/create", json={"passphrase": "short", "display_name": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "passphrase_weak"


async def test_validation_errors_do_not_echo_input(vault_client: httpx.AsyncClient) -> None:
    r = await vault_client.post("/api/vault/create", json={"passphrase": PASSPHRASE, "display_name": "x" * 41})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert PASSPHRASE not in r.text
    r = await vault_client.post("/api/vault/unlock", json={"passphrase": ""})
    assert r.status_code == 422


async def test_locked_endpoints_return_401(vault_client: httpx.AsyncClient) -> None:
    for method, path in [("GET", "/api/vault/me"), ("GET", "/api/secrets"), ("DELETE", f"/api/secrets/{SECRET_NAME}")]:
        r = await vault_client.request(method, path)
        assert r.status_code == 401 and r.json()["error"]["code"] == "vault_locked"
    r = await vault_client.put(f"/api/secrets/{SECRET_NAME}", json={"value": "abcdefghij"})
    assert r.status_code == 401


async def test_lock_without_session_is_204(vault_client: httpx.AsyncClient) -> None:
    assert (await vault_client.post("/api/vault/lock")).status_code == 204


async def test_secret_is_encrypted_at_rest_and_readable_server_side(
    vault_client: httpx.AsyncClient,
    vault_repos: tuple[FakeVaultRepository, FakeSecretRepository],
    vault_settings: Settings,
) -> None:
    await vault_client.post("/api/vault/create", json={"passphrase": PASSPHRASE, "display_name": "Nem"})
    await vault_client.put(f"/api/secrets/{SECRET_NAME}", json={"value": SECRET_VALUE})
    _, secrets_repo = vault_repos
    (record,) = secrets_repo.rows.values()
    assert SECRET_VALUE.encode() not in record.ciphertext
    assert record.hint == SECRET_VALUE[-4:]


async def test_vault_isolation(vault_client: httpx.AsyncClient) -> None:
    await vault_client.post("/api/vault/create", json={"passphrase": PASSPHRASE, "display_name": "A"})
    await vault_client.put(f"/api/secrets/{SECRET_NAME}", json={"value": SECRET_VALUE})
    await vault_client.post("/api/vault/lock")
    vault_client.cookies.clear()
    other = "another long passphrase here"
    await vault_client.post("/api/vault/create", json={"passphrase": other, "display_name": "B"})
    r = await vault_client.get("/api/secrets")
    assert r.json()["secrets"][0]["is_set"] is False


async def test_service_get_secret(
    vault_app: FastAPI,
    vault_repos: tuple[FakeVaultRepository, FakeSecretRepository],
    vault_settings: Settings,
) -> None:
    service = VaultService(*vault_repos, SessionStore(60), vault_settings)
    opened = await service.create(PASSPHRASE, "Nem")
    assert await service.get_secret(opened.session, SECRET_NAME) is None
    await service.set_secret(opened.session, SECRET_NAME, SECRET_VALUE)
    assert await service.get_secret(opened.session, SECRET_NAME) == SECRET_VALUE


async def test_rate_limit_returns_429_with_retry_after() -> None:
    settings = make_settings(
        argon2_time_cost=1,
        argon2_memory_cost_kib=64,
        argon2_parallelism=1,
        unlock_rate_limit_attempts=2,
        unlock_rate_limit_window_seconds=60,
    )
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    vaults, secrets_repo = FakeVaultRepository(), FakeSecretRepository()

    def svc(store: SessionStoreDep, cfg: SettingsDep) -> VaultService:
        return VaultService(vaults, secrets_repo, store, cfg)

    app.dependency_overrides[get_vault_service] = svc
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            assert (await client.post("/api/vault/unlock", json={"passphrase": PASSPHRASE})).status_code == 200
        r = await client.post("/api/vault/unlock", json={"passphrase": PASSPHRASE})
        assert r.status_code == 429
        assert r.json()["error"]["code"] == "rate_limited"
        assert 1 <= int(r.headers["retry-after"]) <= 60
        # create shares the same budget
        r = await client.post("/api/vault/create", json={"passphrase": PASSPHRASE, "display_name": "x"})
        assert r.status_code == 429
        # a spoofed header from a non-loopback peer must not dodge the limit (peer here is loopback, so it is trusted:
        # a different CF-Connecting-IP is a different client)
        r = await client.post(
            "/api/vault/unlock", json={"passphrase": PASSPHRASE}, headers={"CF-Connecting-IP": "203.0.113.5"}
        )
        assert r.status_code == 200
