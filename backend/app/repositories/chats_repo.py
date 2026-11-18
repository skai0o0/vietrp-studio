"""Chat persistence. Every method takes `vault_id` and filters on it."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, Message, UsageLog

# Columns `update` may change (state is written by the turn pipeline and PATCH /state).
UPDATABLE_FIELDS = frozenset({"title", "persona_id", "settings", "state"})


@dataclass(frozen=True, slots=True)
class ChatRecord:
    id: uuid.UUID
    vault_id: uuid.UUID
    mode: str
    cast_ids: list[uuid.UUID]
    persona_id: uuid.UUID | None
    pack: dict[str, Any]
    state: dict[str, Any]
    settings: dict[str, Any]
    title: str
    created_at: datetime
    updated_at: datetime
    messages_count: int = 0
    world_id: uuid.UUID | None = None
    opening_id: str | None = None
    parent_chat_id: uuid.UUID | None = None
    forked_at_seq: int | None = None


@dataclass(frozen=True, slots=True)
class UsageRow:
    agent: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost: float
    created_at: datetime


class ChatRepository(Protocol):
    async def create(
        self,
        vault_id: uuid.UUID,
        *,
        mode: str,
        cast_ids: list[uuid.UUID],
        persona_id: uuid.UUID | None,
        pack: dict[str, Any],
        state: dict[str, Any],
        settings: dict[str, Any],
        title: str,
        world_id: uuid.UUID | None = None,
        opening_id: str | None = None,
        parent_chat_id: uuid.UUID | None = None,
        forked_at_seq: int | None = None,
    ) -> ChatRecord: ...

    async def get(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> ChatRecord | None: ...

    async def list_chats(self, vault_id: uuid.UUID, *, limit: int, offset: int) -> list[ChatRecord]:
        """Most recently updated first."""
        ...

    async def update(self, vault_id: uuid.UUID, chat_id: uuid.UUID, fields: dict[str, Any]) -> ChatRecord | None:
        """Sets the given `UPDATABLE_FIELDS` and bumps `updated_at` (an empty dict only touches the chat)."""
        ...

    async def delete(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> bool: ...

    async def usage_rows(self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, *, limit: int) -> list[UsageRow]:
        """Newest first; all of the vault's chats when `chat_id` is None."""
        ...


def _record(row: Chat, count: int) -> ChatRecord:
    return ChatRecord(
        id=row.id,
        vault_id=row.vault_id,
        mode=row.mode,
        cast_ids=list(row.cast_ids or []),
        persona_id=row.persona_id,
        pack=row.pack,
        state=row.state,
        settings=row.settings,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages_count=count,
        world_id=row.world_id,
        opening_id=row.opening_id,
        parent_chat_id=row.parent_chat_id,
        forked_at_seq=row.forked_at_seq,
    )


class SqlChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _count(self, chat_id: uuid.UUID) -> int:
        return int(await self._session.scalar(select(func.count(Message.id)).where(Message.chat_id == chat_id)) or 0)

    async def create(
        self,
        vault_id: uuid.UUID,
        *,
        mode: str,
        cast_ids: list[uuid.UUID],
        persona_id: uuid.UUID | None,
        pack: dict[str, Any],
        state: dict[str, Any],
        settings: dict[str, Any],
        title: str,
        world_id: uuid.UUID | None = None,
        opening_id: str | None = None,
        parent_chat_id: uuid.UUID | None = None,
        forked_at_seq: int | None = None,
    ) -> ChatRecord:
        now = datetime.now(UTC)
        row = Chat(
            id=uuid.uuid4(),
            vault_id=vault_id,
            mode=mode,
            world_id=world_id,
            opening_id=opening_id,
            cast_ids=cast_ids,
            persona_id=persona_id,
            pack=pack,
            state=state,
            settings=settings,
            parent_chat_id=parent_chat_id,
            forked_at_seq=forked_at_seq,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _record(row, 0)

    async def _row(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> Chat | None:
        return await self._session.scalar(select(Chat).where(Chat.id == chat_id, Chat.vault_id == vault_id))

    async def get(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> ChatRecord | None:
        row = await self._row(vault_id, chat_id)
        return _record(row, await self._count(chat_id)) if row else None

    async def list_chats(self, vault_id: uuid.UUID, *, limit: int, offset: int) -> list[ChatRecord]:
        counts = select(Message.chat_id, func.count(Message.id).label("n")).group_by(Message.chat_id).subquery()
        result = await self._session.execute(
            select(Chat, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.chat_id == Chat.id)
            .where(Chat.vault_id == vault_id)
            .order_by(Chat.updated_at.desc(), Chat.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_record(row, int(count)) for row, count in result.all()]

    async def update(self, vault_id: uuid.UUID, chat_id: uuid.UUID, fields: dict[str, Any]) -> ChatRecord | None:
        row = await self._row(vault_id, chat_id)
        if row is None:
            return None
        for name, value in fields.items():
            if name not in UPDATABLE_FIELDS:
                raise ValueError(f"column {name} cannot be updated")
            setattr(row, name, value)
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _record(row, await self._count(chat_id))

    async def delete(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(Chat).where(Chat.id == chat_id, Chat.vault_id == vault_id).returning(Chat.id)
        )
        return result.first() is not None

    async def usage_rows(self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, *, limit: int) -> list[UsageRow]:
        query = select(UsageLog).where(UsageLog.vault_id == vault_id)
        if chat_id is not None:
            query = query.where(UsageLog.chat_id == chat_id)
        rows = await self._session.scalars(query.order_by(UsageLog.id.desc()).limit(limit))
        return [
            UsageRow(
                r.agent,
                r.model,
                r.prompt_tokens,
                r.completion_tokens,
                r.reasoning_tokens,
                float(r.cost or 0),
                r.created_at,
            )
            for r in rows
        ]
