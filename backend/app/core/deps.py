"""Shared FastAPI dependencies. Later work packages append to this module."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import ApiKeyProvider, LLMGateway
from app.core.client_ip import resolve_client_ip
from app.core.config import Settings, get_settings
from app.core.db import get_session, get_sessionmaker
from app.core.errors import AppError
from app.core.ratelimit import SlidingWindowLimiter
from app.core.sessions import SESSION_COOKIE_NAME, SessionStore, VaultSession, set_session_cookie
from app.llm.deps import OPENROUTER_KEY_SECRET, LLMServices, build_llm_services
from app.llm.usage import SqlUsageRecorder

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_session_store(request: Request, settings: SettingsDep) -> SessionStore:
    """One store per app instance, kept on `app.state` so it dies with the process."""
    store: SessionStore | None = getattr(request.app.state, "session_store", None)
    if store is None:
        store = SessionStore(settings.session_ttl_seconds)
        request.app.state.session_store = store
    return store


def get_unlock_limiter(request: Request, settings: SettingsDep) -> SlidingWindowLimiter:
    limiter: SlidingWindowLimiter | None = getattr(request.app.state, "unlock_limiter", None)
    if limiter is None:
        limiter = SlidingWindowLimiter(settings.unlock_rate_limit_attempts, settings.unlock_rate_limit_window_seconds)
        request.app.state.unlock_limiter = limiter
    return limiter


SessionStoreDep = Annotated[SessionStore, Depends(get_session_store)]
UnlockLimiterDep = Annotated[SlidingWindowLimiter, Depends(get_unlock_limiter)]


def get_client_ip(request: Request, settings: SettingsDep) -> str:
    peer = request.client.host if request.client else None
    return resolve_client_ip(peer, request.headers.get("cf-connecting-ip"), settings.trusted_proxy_hosts)


ClientIpDep = Annotated[str, Depends(get_client_ip)]


async def enforce_unlock_rate_limit(client_ip: ClientIpDep, limiter: UnlockLimiterDep) -> None:
    retry_after = limiter.hit(client_ip)
    if retry_after is not None:
        raise AppError(
            "rate_limited",
            "Too many attempts, try again later",
            429,
            headers={"Retry-After": str(retry_after)},
        )


async def get_vault_session(request: Request, store: SessionStoreDep) -> VaultSession | None:
    """The live session for the request cookie (sliding its TTL), or None."""
    return await store.get(request.cookies.get(SESSION_COOKIE_NAME))


async def require_vault(
    response: Response,
    session: Annotated[VaultSession | None, Depends(get_vault_session)],
    store: SessionStoreDep,
    settings: SettingsDep,
) -> VaultSession:
    """Guard for vault-scoped routes: 401 `vault_locked` unless a session is live."""
    if session is None:
        raise AppError("vault_locked", "Vault is locked", 401)
    # Keep the browser cookie in step with the sliding server-side TTL.
    set_session_cookie(response, session.session_id, ttl_seconds=store.ttl_seconds, secure=settings.cookie_secure)
    return session


VaultSessionDep = Annotated[VaultSession, Depends(require_vault)]


# --- LLM wiring ---


def get_llm_services(request: Request, settings: SettingsDep) -> LLMServices:
    """The shared LLM objects. The lifespan builds them; a lazy build covers apps run without a lifespan."""
    services: LLMServices | None = getattr(request.app.state, "llm_services", None)
    if services is None:
        services = build_llm_services(settings)
        request.app.state.llm_services = services
    return services


LLMServicesDep = Annotated[LLMServices, Depends(get_llm_services)]

GatewayFactory = Callable[[VaultSession, uuid.UUID | None], LLMGateway]


def make_key_provider(vault_session: VaultSession) -> ApiKeyProvider:
    """Reads and decrypts the OpenRouter key on every call, in its own short DB session. Nothing is cached."""
    from app.services.vault_service import get_secret

    async def provide() -> str:
        async with get_sessionmaker()() as db:
            key = await get_secret(db, vault_session, OPENROUTER_KEY_SECRET)
        if not key:
            raise AppError("openrouter_key_missing", "No OpenRouter API key is stored in this vault", 400)
        return key

    return provide


def get_gateway_factory(services: LLMServicesDep) -> GatewayFactory:
    """Builds one `LLMGateway` per turn for a vault session; usage is written to `usage_log`."""

    def build(vault_session: VaultSession, chat_id: uuid.UUID | None) -> LLMGateway:
        return LLMGateway(
            services,
            vault_id=vault_session.vault_id,
            chat_id=chat_id,
            api_key=make_key_provider(vault_session),
            recorder=SqlUsageRecorder(get_sessionmaker()),
        )

    return build


GatewayFactoryDep = Annotated[GatewayFactory, Depends(get_gateway_factory)]
