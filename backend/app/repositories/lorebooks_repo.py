"""Lorebook persistence: the book row, its entries, and the `lorebook_links` back-references."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import Lorebook, LorebookLink, LoreEntry
from app.models.vault import Vault
from app.repositories.characters_repo import Cursor, escape_like


@dataclass(frozen=True, slots=True)
class LorebookRecord:
    id: uuid.UUID
    vault_id: uuid.UUID
    visibility: str
    name: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    author: str
    entry_count: int = 0
    # Loaded by `get_visible`; listings leave it empty and only fill `entry_count`.
    entries: list[dict[str, Any]] = field(default_factory=list)


class LorebookRepository(Protocol):
    async def create(
        self,
        vault_id: uuid.UUID,
        *,
        name: str,
        visibility: str,
        settings: dict[str, Any],
        entries: list[dict[str, Any]],
    ) -> LorebookRecord: ...

    async def get_visible(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookRecord | None: ...

    async def update(
        self,
        vault_id: uuid.UUID,
        lorebook_id: uuid.UUID,
        *,
        name: str,
        visibility: str,
        settings: dict[str, Any],
        entries: list[dict[str, Any]],
    ) -> LorebookRecord | None: ...

    async def delete(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> bool: ...

    async def list_owned(
        self, vault_id: uuid.UUID, *, q: str | None, limit: int, cursor: Cursor | None
    ) -> list[LorebookRecord]:
        """Up to `limit + 1` rows, newest first, without entries."""
        ...

    async def visible_ids(self, vault_id: uuid.UUID, lorebook_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        """The subset that is the vault's own or public."""
        ...

    async def sync_links(
        self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID, lorebook_ids: list[uuid.UUID]
    ) -> None:
        """Make the vault's links for this target equal to `lorebook_ids` (callers pass visible ids only)."""
        ...

    async def delete_links_for_target(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> None: ...

    async def commit(self) -> None: ...


class SqlLorebookRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _record(self, row: Lorebook, author: str, entries: list[dict[str, Any]], count: int) -> LorebookRecord:
        return LorebookRecord(
            id=row.id,
            vault_id=row.vault_id,
            visibility=row.visibility,
            name=row.name,
            settings=row.settings,
            created_at=row.created_at,
            updated_at=row.updated_at,
            author=author,
            entry_count=count,
            entries=entries,
        )

    async def _with_entries(self, lorebook_id: uuid.UUID) -> LorebookRecord | None:
        stmt = select(Lorebook, Vault.display_name).join(Vault, Vault.id == Lorebook.vault_id)
        row = (await self._session.execute(stmt.where(Lorebook.id == lorebook_id))).first()
        if row is None:
            return None
        entries = list(
            await self._session.scalars(
                select(LoreEntry.data).where(LoreEntry.lorebook_id == lorebook_id).order_by(LoreEntry.sort_order)
            )
        )
        return self._record(row[0], row[1], entries, len(entries))

    async def _replace_entries(
        self, vault_id: uuid.UUID, lorebook_id: uuid.UUID, entries: list[dict[str, Any]]
    ) -> None:
        await self._session.execute(
            delete(LoreEntry).where(LoreEntry.lorebook_id == lorebook_id, LoreEntry.vault_id == vault_id)
        )
        now = datetime.now(UTC)
        for index, entry in enumerate(entries):
            self._session.add(
                LoreEntry(
                    id=uuid.uuid4(),
                    vault_id=vault_id,
                    lorebook_id=lorebook_id,
                    data=entry,
                    sort_order=index,
                    created_at=now,
                    updated_at=now,
                )
            )
        await self._session.flush()

    async def create(
        self,
        vault_id: uuid.UUID,
        *,
        name: str,
        visibility: str,
        settings: dict[str, Any],
        entries: list[dict[str, Any]],
    ) -> LorebookRecord:
        now = datetime.now(UTC)
        lorebook_id = uuid.uuid4()
        self._session.add(
            Lorebook(
                id=lorebook_id,
                vault_id=vault_id,
                name=name,
                visibility=visibility,
                settings=settings,
                created_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()
        await self._replace_entries(vault_id, lorebook_id, entries)
        record = await self._with_entries(lorebook_id)
        assert record is not None
        return record

    async def get_visible(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookRecord | None:
        record = await self._with_entries(lorebook_id)
        if record is None or (record.vault_id != vault_id and record.visibility != "public"):
            return None
        return record

    async def update(
        self,
        vault_id: uuid.UUID,
        lorebook_id: uuid.UUID,
        *,
        name: str,
        visibility: str,
        settings: dict[str, Any],
        entries: list[dict[str, Any]],
    ) -> LorebookRecord | None:
        row = await self._session.scalar(
            select(Lorebook).where(Lorebook.id == lorebook_id, Lorebook.vault_id == vault_id)
        )
        if row is None:
            return None
        row.name = name
        row.visibility = visibility
        row.settings = settings
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        await self._replace_entries(vault_id, lorebook_id, entries)
        return await self._with_entries(lorebook_id)

    async def delete(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(Lorebook).where(Lorebook.id == lorebook_id, Lorebook.vault_id == vault_id).returning(Lorebook.id)
        )
        return result.first() is not None

    async def list_owned(
        self, vault_id: uuid.UUID, *, q: str | None, limit: int, cursor: Cursor | None
    ) -> list[LorebookRecord]:
        count = (
            select(func.count())
            .select_from(LoreEntry)
            .where(LoreEntry.lorebook_id == Lorebook.id)
            .correlate(Lorebook)
            .scalar_subquery()
        )
        stmt = (
            select(Lorebook, Vault.display_name, count)
            .join(Vault, Vault.id == Lorebook.vault_id)
            .where(Lorebook.vault_id == vault_id)
        )
        if q and q.strip():
            stmt = stmt.where(Lorebook.name.ilike(f"%{escape_like(q.strip())}%", escape="\\"))
        if cursor:
            stmt = stmt.where(
                or_(
                    Lorebook.updated_at < cursor.updated_at,
                    and_(Lorebook.updated_at == cursor.updated_at, Lorebook.id < cursor.item_id),
                )
            )
        stmt = stmt.order_by(Lorebook.updated_at.desc(), Lorebook.id.desc()).limit(limit + 1)
        rows = (await self._session.execute(stmt)).all()
        return [self._record(row[0], row[1], [], int(row[2])) for row in rows]

    async def visible_ids(self, vault_id: uuid.UUID, lorebook_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not lorebook_ids:
            return set()
        rows = await self._session.scalars(
            select(Lorebook.id).where(
                Lorebook.id.in_(lorebook_ids), or_(Lorebook.vault_id == vault_id, Lorebook.visibility == "public")
            )
        )
        return set(rows)

    async def sync_links(
        self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID, lorebook_ids: list[uuid.UUID]
    ) -> None:
        wanted = set(lorebook_ids)
        scope = and_(
            LorebookLink.vault_id == vault_id,
            LorebookLink.target_type == target_type,
            LorebookLink.target_id == target_id,
        )
        existing = set(await self._session.scalars(select(LorebookLink.lorebook_id).where(scope)))
        stale = existing - wanted
        if stale:
            await self._session.execute(delete(LorebookLink).where(scope, LorebookLink.lorebook_id.in_(stale)))
        for lorebook_id in wanted - existing:
            self._session.add(
                LorebookLink(
                    id=uuid.uuid4(),
                    vault_id=vault_id,
                    lorebook_id=lorebook_id,
                    target_type=target_type,
                    target_id=target_id,
                )
            )
        await self._session.flush()

    async def delete_links_for_target(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(LorebookLink).where(
                LorebookLink.vault_id == vault_id,
                LorebookLink.target_type == target_type,
                LorebookLink.target_id == target_id,
            )
        )

    async def commit(self) -> None:
        await self._session.commit()
