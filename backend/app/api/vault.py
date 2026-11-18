"""Vault endpoints: unlock, create, lock, me."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.core.deps import SessionStoreDep, SettingsDep, VaultSessionDep, enforce_unlock_rate_limit
from app.core.sessions import SESSION_COOKIE_NAME, clear_session_cookie, set_session_cookie
from app.repositories.vault_repo import VaultRecord
from app.schemas.vault import (
    CreateVaultRequest,
    UnlockRequest,
    UnlockResponse,
    UpdateVaultRequest,
    VaultOut,
    VaultResponse,
)
from app.services.vault_service import OpenedVault, VaultServiceDep

router = APIRouter(prefix="/api/vault", tags=["vault"])


def _vault_out(vault: VaultRecord) -> VaultOut:
    return VaultOut(id=vault.id, display_name=vault.display_name, created_at=vault.created_at)


def _start_session(response: Response, opened: OpenedVault, store_ttl: int, secure: bool) -> None:
    set_session_cookie(response, opened.session.session_id, ttl_seconds=store_ttl, secure=secure)


@router.post("/unlock", response_model=UnlockResponse, dependencies=[Depends(enforce_unlock_rate_limit)])
async def unlock(
    body: UnlockRequest,
    response: Response,
    service: VaultServiceDep,
    store: SessionStoreDep,
    settings: SettingsDep,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> UnlockResponse:
    opened = await service.unlock(body.passphrase, session_cookie)
    if opened is None:
        return UnlockResponse(exists=False)
    _start_session(response, opened, store.ttl_seconds, settings.cookie_secure)
    return UnlockResponse(exists=True, vault=_vault_out(opened.vault))


@router.post(
    "/create",
    response_model=VaultResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_unlock_rate_limit)],
)
async def create(
    body: CreateVaultRequest,
    response: Response,
    service: VaultServiceDep,
    store: SessionStoreDep,
    settings: SettingsDep,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> VaultResponse:
    opened = await service.create(body.passphrase, body.display_name, session_cookie)
    _start_session(response, opened, store.ttl_seconds, settings.cookie_secure)
    return VaultResponse(vault=_vault_out(opened.vault))


@router.post("/lock", status_code=status.HTTP_204_NO_CONTENT)
async def lock(
    service: VaultServiceDep,
    settings: SettingsDep,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> Response:
    await service.lock(session_cookie)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, secure=settings.cookie_secure)
    return response


@router.get("/me", response_model=VaultResponse)
async def get_me(session: VaultSessionDep, service: VaultServiceDep) -> VaultResponse:
    return VaultResponse(vault=_vault_out(await service.get_vault(session)))


@router.patch("/me", response_model=VaultResponse)
async def update_me(body: UpdateVaultRequest, session: VaultSessionDep, service: VaultServiceDep) -> VaultResponse:
    return VaultResponse(vault=_vault_out(await service.rename(session, body.display_name)))
