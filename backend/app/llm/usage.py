"""Token usage value object and the recorder protocol that writes `usage_log` rows."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


def _as_int(value: Any) -> int:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0


class Usage(BaseModel):
    """Token counts and cost of one upstream call. Also the `usage` chat event."""

    type: Literal["usage"] = "usage"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    # Provider-reported cost in USD; None when the provider did not say.
    cost: float | None = None

    @classmethod
    def from_api(cls, raw: object) -> Usage:
        """Parse an OpenRouter `usage` object leniently (missing or null fields become 0 / None)."""
        if not isinstance(raw, dict):
            return cls()
        details = raw.get("completion_tokens_details")
        reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
        cost = raw.get("cost")
        return cls(
            prompt_tokens=_as_int(raw.get("prompt_tokens")),
            completion_tokens=_as_int(raw.get("completion_tokens")),
            reasoning_tokens=_as_int(reasoning if reasoning is not None else raw.get("reasoning_tokens")),
            cost=float(cost) if isinstance(cost, int | float) and not isinstance(cost, bool) else None,
        )

    def __add__(self, other: Usage) -> Usage:
        cost = None if self.cost is None and other.cost is None else (self.cost or 0.0) + (other.cost or 0.0)
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            cost=cost,
        )


@dataclass(frozen=True, slots=True)
class UsageContext:
    """Who a call is billed to."""

    vault_id: uuid.UUID
    chat_id: uuid.UUID | None
    agent: str


class UsageRecorder(Protocol):
    async def record(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, agent: str, model: str, usage: Usage
    ) -> None: ...


class NullUsageRecorder:
    """Discards usage; for tests and tools that run outside a vault."""

    async def record(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, agent: str, model: str, usage: Usage
    ) -> None:
        return None


class SqlUsageRecorder:
    """Inserts one `usage_log` row per call in its own short transaction, independent of the turn's session."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def record(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, agent: str, model: str, usage: Usage
    ) -> None:
        from app.repositories import usage_repo

        async with self._sessionmaker() as session:
            await usage_repo.insert(session, vault_id=vault_id, chat_id=chat_id, agent=agent, model=model, usage=usage)
            await session.commit()


async def record_usage(recorder: UsageRecorder | None, context: UsageContext | None, model: str, usage: Usage) -> None:
    """Record one call. Accounting must never break a turn, so recorder failures are logged and swallowed."""
    if recorder is None:
        return
    if context is None:
        raise ValueError("a usage recorder needs a UsageContext")
    try:
        await recorder.record(context.vault_id, context.chat_id, context.agent, model, usage)
    except Exception:
        logger.warning("failed to record usage for agent=%s model=%s", context.agent, model)
