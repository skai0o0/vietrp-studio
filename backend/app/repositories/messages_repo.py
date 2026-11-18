"""Message and variant persistence. Every method takes `vault_id` and filters on it."""

from __future__ import annotations

import copy
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chat, MemorySnapshot, Message, MessageVariant
from app.models.library import LorebookLink
from app.repositories.chats_repo import ChatRecord


@dataclass(frozen=True, slots=True)
class NewVariant:
    content: str
    draft: str | None = None
    director: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    stopped: bool = False


@dataclass(frozen=True, slots=True)
class VariantRecord:
    idx: int
    content: str
    draft: str | None
    director: dict[str, Any] | None
    usage: dict[str, Any] | None
    stopped: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MessageRecord:
    id: uuid.UUID
    chat_id: uuid.UUID
    seq: int
    speaker: str
    active_variant: int
    meta: dict[str, Any]
    state_before: dict[str, Any] | None
    created_at: datetime
    variants: list[VariantRecord] = field(default_factory=list)

    @property
    def content(self) -> str:
        for variant in self.variants:
            if variant.idx == self.active_variant:
                return variant.content
        return self.variants[0].content if self.variants else ""


@dataclass(frozen=True, slots=True)
class MemorySnapshotRecord:
    id: uuid.UUID
    chat_id: uuid.UUID
    upto_seq: int
    summary: str
    events: list[dict[str, Any]]
    created_at: datetime


class MessageRepository(Protocol):
    async def add(
        self,
        vault_id: uuid.UUID,
        chat_id: uuid.UUID,
        *,
        message_id: uuid.UUID,
        seq: int,
        speaker: str,
        meta: dict[str, Any],
        state_before: dict[str, Any] | None,
        variants: Sequence[NewVariant],
    ) -> MessageRecord: ...

    async def next_seq(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> int: ...

    async def page(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, *, before: int | None, limit: int
    ) -> list[MessageRecord]:
        """The newest `limit` messages with `seq < before` (all when None), oldest first."""
        ...

    async def add_snapshot(
        self,
        vault_id: uuid.UUID,
        chat_id: uuid.UUID,
        *,
        upto_seq: int,
        summary: str,
        events: Sequence[dict[str, Any]],
    ) -> MemorySnapshotRecord: ...

    async def list_snapshots(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> list[MemorySnapshotRecord]:
        """All memory snapshots for a chat, ordered by `upto_seq` then `created_at` ascending."""
        ...

    async def latest_snapshot_at_or_before(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, upto_seq: int
    ) -> MemorySnapshotRecord | None: ...

    async def delete_snapshots_after(self, vault_id: uuid.UUID, chat_id: uuid.UUID, seq: int) -> int: ...

    async def get_message(self, vault_id: uuid.UUID, message_id: uuid.UUID) -> MessageRecord | None: ...

    async def set_active_variant(
        self, vault_id: uuid.UUID, message_id: uuid.UUID, variant_idx: int
    ) -> MessageRecord | None: ...

    async def update_variant_content(
        self, vault_id: uuid.UUID, message_id: uuid.UUID, content: str
    ) -> MessageRecord | None: ...

    async def add_variant(
        self,
        vault_id: uuid.UUID,
        message_id: uuid.UUID,
        variant: NewVariant,
        *,
        meta: dict[str, Any] | None = None,
        activate: bool = True,
    ) -> MessageRecord: ...

    async def delete_from_seq(self, vault_id: uuid.UUID, chat_id: uuid.UUID, min_seq: int) -> int: ...

    async def fork_chat(
        self,
        vault_id: uuid.UUID,
        source_chat: ChatRecord,
        *,
        upto_seq: int,
        initial_state: dict[str, Any],
        title: str,
    ) -> ChatRecord: ...


class SqlMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        vault_id: uuid.UUID,
        chat_id: uuid.UUID,
        *,
        message_id: uuid.UUID,
        seq: int,
        speaker: str,
        meta: dict[str, Any],
        state_before: dict[str, Any] | None,
        variants: Sequence[NewVariant],
    ) -> MessageRecord:
        now = datetime.now(UTC)
        self._session.add(
            Message(
                id=message_id,
                vault_id=vault_id,
                chat_id=chat_id,
                seq=seq,
                speaker=speaker,
                active_variant=0,
                meta=meta,
                state_before=state_before,
                created_at=now,
            )
        )
        # The message row must exist before its variants (foreign key).
        await self._session.flush()
        records: list[VariantRecord] = []
        for idx, variant in enumerate(variants):
            self._session.add(
                MessageVariant(
                    id=uuid.uuid4(),
                    vault_id=vault_id,
                    message_id=message_id,
                    idx=idx,
                    content=variant.content,
                    draft=variant.draft,
                    director=variant.director,
                    usage=variant.usage,
                    stopped=variant.stopped,
                    created_at=now,
                )
            )
            records.append(
                VariantRecord(
                    idx, variant.content, variant.draft, variant.director, variant.usage, variant.stopped, now
                )
            )
        await self._session.flush()
        return MessageRecord(message_id, chat_id, seq, speaker, 0, meta, state_before, now, records)

    async def next_seq(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> int:
        top = await self._session.scalar(
            select(func.max(Message.seq)).where(Message.chat_id == chat_id, Message.vault_id == vault_id)
        )
        return 0 if top is None else int(top) + 1

    async def page(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, *, before: int | None, limit: int
    ) -> list[MessageRecord]:
        query = select(Message).where(Message.chat_id == chat_id, Message.vault_id == vault_id)
        if before is not None:
            query = query.where(Message.seq < before)
        rows = list((await self._session.scalars(query.order_by(Message.seq.desc()).limit(limit))).all())
        rows.reverse()
        if not rows:
            return []
        variants = await self._session.scalars(
            select(MessageVariant)
            .where(MessageVariant.message_id.in_([r.id for r in rows]), MessageVariant.vault_id == vault_id)
            .order_by(MessageVariant.idx)
        )
        by_message: dict[uuid.UUID, list[VariantRecord]] = {}
        for v in variants:
            by_message.setdefault(v.message_id, []).append(
                VariantRecord(v.idx, v.content, v.draft, v.director, v.usage, v.stopped, v.created_at)
            )
        return [
            MessageRecord(
                r.id,
                r.chat_id,
                r.seq,
                r.speaker,
                r.active_variant,
                r.meta,
                r.state_before,
                r.created_at,
                by_message.get(r.id, []),
            )
            for r in rows
        ]

    @staticmethod
    def _snapshot_record(row: MemorySnapshot) -> MemorySnapshotRecord:
        return MemorySnapshotRecord(
            id=row.id,
            chat_id=row.chat_id,
            upto_seq=row.upto_seq,
            summary=row.summary,
            events=[dict(ev) for ev in (row.events or []) if isinstance(ev, dict)],
            created_at=row.created_at,
        )

    async def add_snapshot(
        self,
        vault_id: uuid.UUID,
        chat_id: uuid.UUID,
        *,
        upto_seq: int,
        summary: str,
        events: Sequence[dict[str, Any]],
    ) -> MemorySnapshotRecord:
        now = datetime.now(UTC)
        snapshot_id = uuid.uuid4()
        stored_events = [dict(ev) for ev in events]
        row = MemorySnapshot(
            id=snapshot_id,
            vault_id=vault_id,
            chat_id=chat_id,
            upto_seq=upto_seq,
            summary=summary,
            events=stored_events,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return MemorySnapshotRecord(snapshot_id, chat_id, upto_seq, summary, stored_events, now)

    async def list_snapshots(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> list[MemorySnapshotRecord]:
        rows = await self._session.scalars(
            select(MemorySnapshot)
            .where(MemorySnapshot.chat_id == chat_id, MemorySnapshot.vault_id == vault_id)
            .order_by(MemorySnapshot.upto_seq.asc(), MemorySnapshot.created_at.asc())
        )
        return [self._snapshot_record(row) for row in rows]

    async def latest_snapshot_at_or_before(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, upto_seq: int
    ) -> MemorySnapshotRecord | None:
        row = await self._session.scalar(
            select(MemorySnapshot)
            .where(
                MemorySnapshot.chat_id == chat_id,
                MemorySnapshot.vault_id == vault_id,
                MemorySnapshot.upto_seq <= upto_seq,
            )
            .order_by(MemorySnapshot.upto_seq.desc(), MemorySnapshot.created_at.desc())
            .limit(1)
        )
        return self._snapshot_record(row) if row is not None else None

    async def delete_snapshots_after(self, vault_id: uuid.UUID, chat_id: uuid.UUID, seq: int) -> int:
        result = await self._session.execute(
            delete(MemorySnapshot)
            .where(
                MemorySnapshot.chat_id == chat_id,
                MemorySnapshot.vault_id == vault_id,
                MemorySnapshot.upto_seq > seq,
            )
            .returning(MemorySnapshot.id)
        )
        return len(result.all())

    async def _variants_for_messages(
        self, vault_id: uuid.UUID, message_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[VariantRecord]]:
        if not message_ids:
            return {}
        variants = await self._session.scalars(
            select(MessageVariant)
            .where(MessageVariant.message_id.in_(message_ids), MessageVariant.vault_id == vault_id)
            .order_by(MessageVariant.idx)
        )
        by_message: dict[uuid.UUID, list[VariantRecord]] = {}
        for v in variants:
            by_message.setdefault(v.message_id, []).append(
                VariantRecord(v.idx, v.content, v.draft, v.director, v.usage, v.stopped, v.created_at)
            )
        return by_message

    @staticmethod
    def _to_message_record(row: Message, variants: list[VariantRecord]) -> MessageRecord:
        return MessageRecord(
            row.id,
            row.chat_id,
            row.seq,
            row.speaker,
            row.active_variant,
            row.meta,
            row.state_before,
            row.created_at,
            variants,
        )

    async def get_message(self, vault_id: uuid.UUID, message_id: uuid.UUID) -> MessageRecord | None:
        row = await self._session.scalar(select(Message).where(Message.id == message_id, Message.vault_id == vault_id))
        if row is None:
            return None
        variants = await self._variants_for_messages(vault_id, [row.id])
        return self._to_message_record(row, variants.get(row.id, []))

    async def set_active_variant(
        self, vault_id: uuid.UUID, message_id: uuid.UUID, variant_idx: int
    ) -> MessageRecord | None:
        row = await self._session.scalar(select(Message).where(Message.id == message_id, Message.vault_id == vault_id))
        if row is None:
            return None
        variant = await self._session.scalar(
            select(MessageVariant).where(
                MessageVariant.message_id == message_id,
                MessageVariant.vault_id == vault_id,
                MessageVariant.idx == variant_idx,
            )
        )
        if variant is None:
            raise ValueError("variant_not_found")
        row.active_variant = variant_idx
        await self._session.flush()
        return await self.get_message(vault_id, message_id)

    async def update_variant_content(
        self, vault_id: uuid.UUID, message_id: uuid.UUID, content: str
    ) -> MessageRecord | None:
        row = await self._session.scalar(select(Message).where(Message.id == message_id, Message.vault_id == vault_id))
        if row is None:
            return None
        variant = await self._session.scalar(
            select(MessageVariant).where(
                MessageVariant.message_id == message_id,
                MessageVariant.vault_id == vault_id,
                MessageVariant.idx == row.active_variant,
            )
        )
        if variant is None:
            raise ValueError("variant_not_found")
        variant.content = content
        await self._session.flush()
        return await self.get_message(vault_id, message_id)

    async def add_variant(
        self,
        vault_id: uuid.UUID,
        message_id: uuid.UUID,
        variant: NewVariant,
        *,
        meta: dict[str, Any] | None = None,
        activate: bool = True,
    ) -> MessageRecord:
        row = await self._session.scalar(select(Message).where(Message.id == message_id, Message.vault_id == vault_id))
        if row is None:
            raise ValueError("message_not_found")
        top = await self._session.scalar(
            select(func.max(MessageVariant.idx)).where(
                MessageVariant.message_id == message_id,
                MessageVariant.vault_id == vault_id,
            )
        )
        next_idx = 0 if top is None else int(top) + 1
        now = datetime.now(UTC)
        self._session.add(
            MessageVariant(
                id=uuid.uuid4(),
                vault_id=vault_id,
                message_id=message_id,
                idx=next_idx,
                content=variant.content,
                draft=variant.draft,
                director=variant.director,
                usage=variant.usage,
                stopped=variant.stopped,
                created_at=now,
            )
        )
        if activate:
            row.active_variant = next_idx
        if meta is not None:
            row.meta = copy.deepcopy(meta)
        await self._session.flush()
        updated = await self.get_message(vault_id, message_id)
        assert updated is not None
        return updated

    async def delete_from_seq(self, vault_id: uuid.UUID, chat_id: uuid.UUID, min_seq: int) -> int:
        result = await self._session.execute(
            delete(Message)
            .where(
                Message.vault_id == vault_id,
                Message.chat_id == chat_id,
                Message.seq >= min_seq,
            )
            .returning(Message.id)
        )
        await self._session.flush()
        return len(result.all())

    async def fork_chat(
        self,
        vault_id: uuid.UUID,
        source_chat: ChatRecord,
        *,
        upto_seq: int,
        initial_state: dict[str, Any],
        title: str,
    ) -> ChatRecord:
        assert source_chat.vault_id == vault_id
        now = datetime.now(UTC)
        new_chat_id = uuid.uuid4()
        new_chat = Chat(
            id=new_chat_id,
            vault_id=vault_id,
            mode=source_chat.mode,
            world_id=source_chat.world_id,
            opening_id=source_chat.opening_id,
            cast_ids=list(source_chat.cast_ids),
            persona_id=source_chat.persona_id,
            pack=copy.deepcopy(source_chat.pack),
            state=copy.deepcopy(initial_state),
            settings=copy.deepcopy(source_chat.settings),
            parent_chat_id=source_chat.id,
            forked_at_seq=upto_seq,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._session.add(new_chat)
        await self._session.flush()

        src_messages = list(
            (
                await self._session.scalars(
                    select(Message)
                    .where(
                        Message.vault_id == vault_id,
                        Message.chat_id == source_chat.id,
                        Message.seq <= upto_seq,
                    )
                    .order_by(Message.seq.asc())
                )
            ).all()
        )
        src_variants = (
            list(
                (
                    await self._session.scalars(
                        select(MessageVariant)
                        .where(
                            MessageVariant.vault_id == vault_id,
                            MessageVariant.message_id.in_([m.id for m in src_messages]),
                        )
                        .order_by(MessageVariant.idx.asc())
                    )
                ).all()
            )
            if src_messages
            else []
        )
        variants_by_msg: dict[uuid.UUID, list[MessageVariant]] = {}
        for v in src_variants:
            variants_by_msg.setdefault(v.message_id, []).append(v)

        id_map: dict[uuid.UUID, uuid.UUID] = {}
        for m in src_messages:
            new_msg_id = uuid.uuid4()
            id_map[m.id] = new_msg_id
            self._session.add(
                Message(
                    id=new_msg_id,
                    vault_id=vault_id,
                    chat_id=new_chat_id,
                    seq=m.seq,
                    speaker=m.speaker,
                    active_variant=m.active_variant,
                    meta=copy.deepcopy(m.meta),
                    state_before=copy.deepcopy(m.state_before),
                    created_at=m.created_at,
                )
            )
        if src_messages:
            await self._session.flush()
            for m in src_messages:
                new_msg_id = id_map[m.id]
                for v in variants_by_msg.get(m.id, []):
                    self._session.add(
                        MessageVariant(
                            id=uuid.uuid4(),
                            vault_id=vault_id,
                            message_id=new_msg_id,
                            idx=v.idx,
                            content=v.content,
                            draft=v.draft,
                            director=copy.deepcopy(v.director),
                            usage=copy.deepcopy(v.usage),
                            stopped=v.stopped,
                            created_at=v.created_at,
                        )
                    )

        src_snapshots = list(
            (
                await self._session.scalars(
                    select(MemorySnapshot)
                    .where(
                        MemorySnapshot.vault_id == vault_id,
                        MemorySnapshot.chat_id == source_chat.id,
                        MemorySnapshot.upto_seq <= upto_seq + 1,
                    )
                    .order_by(MemorySnapshot.upto_seq.asc(), MemorySnapshot.created_at.asc())
                )
            ).all()
        )
        for snap in src_snapshots:
            self._session.add(
                MemorySnapshot(
                    id=uuid.uuid4(),
                    vault_id=vault_id,
                    chat_id=new_chat_id,
                    upto_seq=snap.upto_seq,
                    summary=snap.summary,
                    events=copy.deepcopy(snap.events),
                    created_at=snap.created_at,
                )
            )

        src_links = list(
            (
                await self._session.scalars(
                    select(LorebookLink).where(
                        LorebookLink.vault_id == vault_id,
                        LorebookLink.target_type == "chat",
                        LorebookLink.target_id == source_chat.id,
                    )
                )
            ).all()
        )
        for link in src_links:
            self._session.add(
                LorebookLink(
                    id=uuid.uuid4(),
                    vault_id=vault_id,
                    lorebook_id=link.lorebook_id,
                    target_type="chat",
                    target_id=new_chat_id,
                )
            )

        await self._session.flush()
        return ChatRecord(
            id=new_chat.id,
            vault_id=new_chat.vault_id,
            mode=new_chat.mode,
            cast_ids=list(new_chat.cast_ids or []),
            persona_id=new_chat.persona_id,
            pack=new_chat.pack,
            state=new_chat.state,
            settings=new_chat.settings,
            title=new_chat.title,
            created_at=new_chat.created_at,
            updated_at=new_chat.updated_at,
            messages_count=len(src_messages),
            world_id=new_chat.world_id,
            opening_id=new_chat.opening_id,
            parent_chat_id=new_chat.parent_chat_id,
            forked_at_seq=new_chat.forked_at_seq,
        )
