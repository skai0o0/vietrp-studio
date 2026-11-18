"""In-memory vault sessions. The DEK lives only here; a server restart clears everything by design."""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from starlette.responses import Response

SESSION_COOKIE_NAME = "vietrp_session"
SESSION_ID_BYTES = 32  # secrets.token_urlsafe(32) gives 256 bits of entropy


@dataclass(slots=True)
class VaultSession:
    session_id: str
    vault_id: uuid.UUID
    dek: bytes = field(repr=False)
    expires_at: float


def set_session_cookie(response: Response, session_id: str, *, ttl_seconds: int, secure: bool) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=ttl_seconds,
        path="/",
        httponly=True,
        samesite="strict",
        secure=secure,
    )


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=secure)


class SessionStore:
    """Sliding-TTL session map. `clock` is injectable so tests can move time without sleeping."""

    def __init__(self, ttl_seconds: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._sessions: dict[str, VaultSession] = {}
        self._lock = asyncio.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl

    async def create(self, vault_id: uuid.UUID, dek: bytes) -> VaultSession:
        session_id = secrets.token_urlsafe(SESSION_ID_BYTES)
        session = VaultSession(session_id, vault_id, dek, self._clock() + self._ttl)
        async with self._lock:
            self._sessions[session_id] = session
        return session

    async def get(self, session_id: str | None) -> VaultSession | None:
        """Return the live session and slide its expiry; expired sessions are removed."""
        if not session_id:
            return None
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            now = self._clock()
            if session.expires_at <= now:
                del self._sessions[session_id]
                return None
            session.expires_at = now + self._ttl
            return session

    async def remove(self, session_id: str | None) -> None:
        if not session_id:
            return
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def purge_expired(self) -> int:
        async with self._lock:
            now = self._clock()
            expired = [sid for sid, s in self._sessions.items() if s.expires_at <= now]
            for sid in expired:
                del self._sessions[sid]
            return len(expired)
