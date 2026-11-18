"""SQL for `usage_log`. Every method takes `vault_id`; there is no unscoped read."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.usage import Usage
from app.models.chat import UsageLog


async def insert(
    session: AsyncSession,
    *,
    vault_id: uuid.UUID,
    chat_id: uuid.UUID | None,
    agent: str,
    model: str,
    usage: Usage,
) -> UsageLog:
    row = UsageLog(
        vault_id=vault_id,
        chat_id=chat_id,
        agent=agent,
        model=model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cost=None if usage.cost is None else Decimal(str(usage.cost)),
    )
    session.add(row)
    await session.flush()
    return row


async def list_recent(session: AsyncSession, *, vault_id: uuid.UUID, limit: int) -> list[UsageLog]:
    result = await session.execute(
        select(UsageLog).where(UsageLog.vault_id == vault_id).order_by(UsageLog.id.desc()).limit(limit)
    )
    return list(result.scalars())


@dataclass(frozen=True, slots=True)
class UsageTotals:
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost: Decimal


async def totals_for_chat(session: AsyncSession, *, vault_id: uuid.UUID, chat_id: uuid.UUID) -> UsageTotals:
    """Sum of one chat's usage rows (unknown costs count as 0)."""
    row = (
        await session.execute(
            select(
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.prompt_tokens), 0),
                func.coalesce(func.sum(UsageLog.completion_tokens), 0),
                func.coalesce(func.sum(UsageLog.cost), 0),
            ).where(UsageLog.vault_id == vault_id, UsageLog.chat_id == chat_id)
        )
    ).one()
    return UsageTotals(int(row[0]), int(row[1]), int(row[2]), Decimal(str(row[3])))
