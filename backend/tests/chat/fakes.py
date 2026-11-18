"""In-memory chat, message and preset repositories (they mirror the SQL semantics) plus a fake unit of work."""

from __future__ import annotations

import copy
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from app.repositories.chats_repo import UPDATABLE_FIELDS, ChatRecord, UsageRow
from app.repositories.messages_repo import MemorySnapshotRecord, MessageRecord, NewVariant, VariantRecord
from app.repositories.presets_repo import PresetRecord
from app.services.chat_service import ChatRepos, UnitOfWork
from app.services.library_service import Repos

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass
class ChatStore:
    chats: dict[uuid.UUID, ChatRecord] = field(default_factory=dict)
    messages: dict[uuid.UUID, list[MessageRecord]] = field(default_factory=dict)
    snapshots: dict[uuid.UUID, list[MemorySnapshotRecord]] = field(default_factory=dict)
    presets: dict[uuid.UUID, PresetRecord] = field(default_factory=dict)
    ticks: int = 0

    def now(self) -> datetime:
        self.ticks += 1
        return _EPOCH + timedelta(seconds=self.ticks)


class FakeChatRepository:
    def __init__(self, store: ChatStore) -> None:
        self._s = store

    def _count(self, chat: ChatRecord) -> ChatRecord:
        return replace(chat, messages_count=len(self._s.messages.get(chat.id, [])))

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
        now = self._s.now()
        record = ChatRecord(
            uuid.uuid4(),
            vault_id,
            mode,
            cast_ids,
            persona_id,
            copy.deepcopy(pack),
            copy.deepcopy(state),
            copy.deepcopy(settings),
            title,
            now,
            now,
            0,
            world_id,
            opening_id,
            parent_chat_id,
            forked_at_seq,
        )
        self._s.chats[record.id] = record
        self._s.messages[record.id] = []
        self._s.snapshots[record.id] = []
        return record

    async def get(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> ChatRecord | None:
        chat = self._s.chats.get(chat_id)
        return self._count(chat) if chat and chat.vault_id == vault_id else None

    async def list_chats(self, vault_id: uuid.UUID, *, limit: int, offset: int) -> list[ChatRecord]:
        rows = sorted((c for c in self._s.chats.values() if c.vault_id == vault_id), key=lambda c: c.updated_at)
        return [self._count(c) for c in reversed(rows)][offset : offset + limit]

    async def update(self, vault_id: uuid.UUID, chat_id: uuid.UUID, fields: dict[str, Any]) -> ChatRecord | None:
        chat = self._s.chats.get(chat_id)
        if chat is None or chat.vault_id != vault_id:
            return None
        assert set(fields) <= UPDATABLE_FIELDS
        updated = replace(chat, updated_at=self._s.now(), **copy.deepcopy(fields))
        self._s.chats[chat_id] = updated
        return self._count(updated)

    async def delete(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> bool:
        chat = self._s.chats.get(chat_id)
        if chat is None or chat.vault_id != vault_id:
            return False
        del self._s.chats[chat_id]
        self._s.messages.pop(chat_id, None)
        self._s.snapshots.pop(chat_id, None)
        return True

    async def usage_rows(self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, *, limit: int) -> list[UsageRow]:
        return []


class FakeMessageRepository:
    def __init__(self, store: ChatStore) -> None:
        self._s = store

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
        chat = self._s.chats.get(chat_id)
        assert chat is not None and chat.vault_id == vault_id
        now = self._s.now()
        record = MessageRecord(
            message_id,
            chat_id,
            seq,
            speaker,
            0,
            copy.deepcopy(meta),
            copy.deepcopy(state_before),
            now,
            [VariantRecord(i, v.content, v.draft, v.director, v.usage, v.stopped, now) for i, v in enumerate(variants)],
        )
        self._s.messages[chat_id].append(record)
        return record

    async def next_seq(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> int:
        rows = self._s.messages.get(chat_id, [])
        return max((m.seq for m in rows), default=-1) + 1

    async def page(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, *, before: int | None, limit: int
    ) -> list[MessageRecord]:
        chat = self._s.chats.get(chat_id)
        if chat is None or chat.vault_id != vault_id:
            return []
        rows = sorted(self._s.messages.get(chat_id, []), key=lambda m: m.seq)
        if before is not None:
            rows = [m for m in rows if m.seq < before]
        return rows[-limit:]

    async def add_snapshot(
        self,
        vault_id: uuid.UUID,
        chat_id: uuid.UUID,
        *,
        upto_seq: int,
        summary: str,
        events: Sequence[dict[str, Any]],
    ) -> MemorySnapshotRecord:
        chat = self._s.chats.get(chat_id)
        assert chat is not None and chat.vault_id == vault_id
        now = self._s.now()
        stored_events = copy.deepcopy([dict(ev) for ev in events])
        record = MemorySnapshotRecord(uuid.uuid4(), chat_id, upto_seq, summary, stored_events, now)
        self._s.snapshots.setdefault(chat_id, []).append(record)
        return record

    async def list_snapshots(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> list[MemorySnapshotRecord]:
        chat = self._s.chats.get(chat_id)
        if chat is None or chat.vault_id != vault_id:
            return []
        rows = sorted(self._s.snapshots.get(chat_id, []), key=lambda s: (s.upto_seq, s.created_at))
        return [
            MemorySnapshotRecord(s.id, s.chat_id, s.upto_seq, s.summary, copy.deepcopy(s.events), s.created_at)
            for s in rows
        ]

    async def latest_snapshot_at_or_before(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID, upto_seq: int
    ) -> MemorySnapshotRecord | None:
        chat = self._s.chats.get(chat_id)
        if chat is None or chat.vault_id != vault_id:
            return None
        eligible = [s for s in self._s.snapshots.get(chat_id, []) if s.upto_seq <= upto_seq]
        if not eligible:
            return None
        latest = max(eligible, key=lambda s: (s.upto_seq, s.created_at))
        return MemorySnapshotRecord(
            latest.id,
            latest.chat_id,
            latest.upto_seq,
            latest.summary,
            copy.deepcopy(latest.events),
            latest.created_at,
        )

    async def delete_snapshots_after(self, vault_id: uuid.UUID, chat_id: uuid.UUID, seq: int) -> int:
        chat = self._s.chats.get(chat_id)
        if chat is None or chat.vault_id != vault_id:
            return 0
        existing = self._s.snapshots.get(chat_id, [])
        kept = [s for s in existing if s.upto_seq <= seq]
        removed = len(existing) - len(kept)
        self._s.snapshots[chat_id] = kept
        return removed

    @staticmethod
    def _clone_message(record: MessageRecord) -> MessageRecord:
        return MessageRecord(
            id=record.id,
            chat_id=record.chat_id,
            seq=record.seq,
            speaker=record.speaker,
            active_variant=record.active_variant,
            meta=copy.deepcopy(record.meta),
            state_before=copy.deepcopy(record.state_before),
            created_at=record.created_at,
            variants=[
                VariantRecord(
                    v.idx,
                    v.content,
                    v.draft,
                    copy.deepcopy(v.director),
                    copy.deepcopy(v.usage),
                    v.stopped,
                    v.created_at,
                )
                for v in sorted(record.variants, key=lambda item: item.idx)
            ],
        )

    def _find_message(self, vault_id: uuid.UUID, message_id: uuid.UUID) -> tuple[uuid.UUID, int, MessageRecord] | None:
        for chat_id, rows in self._s.messages.items():
            chat = self._s.chats.get(chat_id)
            if chat is None or chat.vault_id != vault_id:
                continue
            for idx, msg in enumerate(rows):
                if msg.id == message_id:
                    return chat_id, idx, msg
        return None

    async def get_message(self, vault_id: uuid.UUID, message_id: uuid.UUID) -> MessageRecord | None:
        found = self._find_message(vault_id, message_id)
        return self._clone_message(found[2]) if found is not None else None

    async def set_active_variant(
        self, vault_id: uuid.UUID, message_id: uuid.UUID, variant_idx: int
    ) -> MessageRecord | None:
        found = self._find_message(vault_id, message_id)
        if found is None:
            return None
        chat_id, pos, msg = found
        if not any(v.idx == variant_idx for v in msg.variants):
            raise ValueError("variant_not_found")
        updated = replace(msg, active_variant=variant_idx)
        self._s.messages[chat_id][pos] = updated
        return self._clone_message(updated)

    async def update_variant_content(
        self, vault_id: uuid.UUID, message_id: uuid.UUID, content: str
    ) -> MessageRecord | None:
        found = self._find_message(vault_id, message_id)
        if found is None:
            return None
        chat_id, pos, msg = found
        new_variants: list[VariantRecord] = []
        matched = False
        for v in msg.variants:
            if v.idx == msg.active_variant:
                matched = True
                new_variants.append(replace(v, content=content))
            else:
                new_variants.append(v)
        if not matched:
            raise ValueError("variant_not_found")
        updated = replace(msg, variants=new_variants)
        self._s.messages[chat_id][pos] = updated
        return self._clone_message(updated)

    async def add_variant(
        self,
        vault_id: uuid.UUID,
        message_id: uuid.UUID,
        variant: NewVariant,
        *,
        meta: dict[str, Any] | None = None,
        activate: bool = True,
    ) -> MessageRecord:
        found = self._find_message(vault_id, message_id)
        if found is None:
            raise ValueError("message_not_found")
        chat_id, pos, msg = found
        next_idx = max((v.idx for v in msg.variants), default=-1) + 1
        now = self._s.now()
        new_var = VariantRecord(
            next_idx,
            variant.content,
            variant.draft,
            copy.deepcopy(variant.director),
            copy.deepcopy(variant.usage),
            variant.stopped,
            now,
        )
        updated = replace(
            msg,
            active_variant=next_idx if activate else msg.active_variant,
            meta=copy.deepcopy(meta) if meta is not None else msg.meta,
            variants=[*msg.variants, new_var],
        )
        self._s.messages[chat_id][pos] = updated
        return self._clone_message(updated)

    async def delete_from_seq(self, vault_id: uuid.UUID, chat_id: uuid.UUID, min_seq: int) -> int:
        chat = self._s.chats.get(chat_id)
        if chat is None or chat.vault_id != vault_id:
            return 0
        existing = self._s.messages.get(chat_id, [])
        kept = [m for m in existing if m.seq < min_seq]
        removed = len(existing) - len(kept)
        self._s.messages[chat_id] = kept
        return removed

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
        now = self._s.now()
        new_chat_id = uuid.uuid4()
        copied_msgs: list[MessageRecord] = []
        for m in sorted(self._s.messages.get(source_chat.id, []), key=lambda item: item.seq):
            if m.seq > upto_seq:
                continue
            new_msg_id = uuid.uuid4()
            copied_msgs.append(
                MessageRecord(
                    id=new_msg_id,
                    chat_id=new_chat_id,
                    seq=m.seq,
                    speaker=m.speaker,
                    active_variant=m.active_variant,
                    meta=copy.deepcopy(m.meta),
                    state_before=copy.deepcopy(m.state_before),
                    created_at=m.created_at,
                    variants=[
                        VariantRecord(
                            v.idx,
                            v.content,
                            v.draft,
                            copy.deepcopy(v.director),
                            copy.deepcopy(v.usage),
                            v.stopped,
                            v.created_at,
                        )
                        for v in sorted(m.variants, key=lambda item: item.idx)
                    ],
                )
            )
        copied_snaps = [
            MemorySnapshotRecord(
                id=uuid.uuid4(),
                chat_id=new_chat_id,
                upto_seq=s.upto_seq,
                summary=s.summary,
                events=copy.deepcopy(s.events),
                created_at=s.created_at,
            )
            for s in sorted(
                self._s.snapshots.get(source_chat.id, []), key=lambda item: (item.upto_seq, item.created_at)
            )
            if s.upto_seq <= upto_seq + 1
        ]
        new_chat = ChatRecord(
            id=new_chat_id,
            vault_id=vault_id,
            mode=source_chat.mode,
            cast_ids=list(source_chat.cast_ids),
            persona_id=source_chat.persona_id,
            pack=copy.deepcopy(source_chat.pack),
            state=copy.deepcopy(initial_state),
            settings=copy.deepcopy(source_chat.settings),
            title=title,
            created_at=now,
            updated_at=now,
            messages_count=len(copied_msgs),
            world_id=source_chat.world_id,
            opening_id=source_chat.opening_id,
            parent_chat_id=source_chat.id,
            forked_at_seq=upto_seq,
        )
        self._s.chats[new_chat_id] = new_chat
        self._s.messages[new_chat_id] = copied_msgs
        self._s.snapshots[new_chat_id] = copied_snaps
        return new_chat


class FakePresetRepository:
    def __init__(self, store: ChatStore) -> None:
        self._s = store

    async def list_presets(self, vault_id: uuid.UUID, *, agent: str | None) -> list[PresetRecord]:
        rows = [p for p in self._s.presets.values() if p.vault_id == vault_id and agent in (None, p.agent)]
        return sorted(rows, key=lambda p: p.updated_at, reverse=True)

    async def get(self, vault_id: uuid.UUID, preset_id: uuid.UUID) -> PresetRecord | None:
        row = self._s.presets.get(preset_id)
        return row if row and row.vault_id == vault_id else None

    async def create(self, vault_id: uuid.UUID, *, agent: str, name: str, layers: dict[str, str]) -> PresetRecord:
        now = self._s.now()
        row = PresetRecord(uuid.uuid4(), vault_id, agent, name, dict(layers), now, now)
        self._s.presets[row.id] = row
        return row

    async def update(
        self, vault_id: uuid.UUID, preset_id: uuid.UUID, *, agent: str, name: str, layers: dict[str, str]
    ) -> PresetRecord | None:
        row = await self.get(vault_id, preset_id)
        if row is None:
            return None
        new = replace(row, agent=agent, name=name, layers=dict(layers), updated_at=self._s.now())
        self._s.presets[preset_id] = new
        return new

    async def delete(self, vault_id: uuid.UUID, preset_id: uuid.UUID) -> bool:
        if await self.get(vault_id, preset_id) is None:
            return False
        del self._s.presets[preset_id]
        return True


async def _no_commit() -> None:
    return None


def fake_unit_of_work(store: ChatStore, library: Repos) -> UnitOfWork:
    @asynccontextmanager
    async def begin() -> AsyncIterator[ChatRepos]:
        yield ChatRepos(
            chats=FakeChatRepository(store),
            messages=FakeMessageRepository(store),
            presets=FakePresetRepository(store),
            library=library,
            commit=_no_commit,
        )

    return begin
