"""In-memory repositories for the library API tests; they mirror the SQL semantics."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from app.repositories.assets_repo import AssetRecord
from app.repositories.characters_repo import ContentRecord, Cursor, Sort
from app.repositories.creator_repo import UPDATABLE_FIELDS, CreatorSessionRecord
from app.repositories.lorebooks_repo import LorebookRecord
from app.repositories.personas_repo import PersonaRecord
from app.services.library_service import Repos
from tests.vault.fakes import FakeVaultRepository

_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


class FakeStore:
    """Shared state of one fake database, with a clock that gives every write a distinct timestamp."""

    def __init__(self, vaults: FakeVaultRepository) -> None:
        self.vaults = vaults
        self.favorites: list[tuple[uuid.UUID, str, uuid.UUID]] = []
        self.links: set[tuple[uuid.UUID, str, uuid.UUID, uuid.UUID]] = set()
        self.assets: dict[uuid.UUID, AssetRecord] = {}
        self.content: dict[str, dict[uuid.UUID, ContentRecord]] = {"character": {}, "world": {}}
        self.lorebooks: dict[uuid.UUID, LorebookRecord] = {}
        self.creator_sessions: dict[uuid.UUID, CreatorSessionRecord] = {}
        self._ticks = 0

    def now(self) -> datetime:
        self._ticks += 1
        return _EPOCH + timedelta(seconds=self._ticks)

    def author(self, vault_id: uuid.UUID) -> str:
        return self.vaults.rows[vault_id].display_name


class FakeContentRepository:
    def __init__(self, store: FakeStore, target_type: str) -> None:
        self._store = store
        self._type = target_type
        self.rows = store.content[target_type]

    def _decorate(self, row: ContentRecord, viewer: uuid.UUID | None) -> ContentRecord:
        count = sum(1 for _, t, i in self._store.favorites if t == self._type and i == row.id)
        is_fav = viewer is not None and (viewer, self._type, row.id) in self._store.favorites
        return replace(row, favorite_count=count, is_favorite=is_fav, author=self._store.author(row.vault_id))

    async def create(self, vault_id: uuid.UUID, *, data: dict[str, Any], visibility: str) -> ContentRecord:
        now = self._store.now()
        row = ContentRecord(uuid.uuid4(), vault_id, visibility, copy.deepcopy(data), None, now, now, "")
        self.rows[row.id] = row
        return self._decorate(row, None)

    async def get_owned(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ContentRecord | None:
        row = self.rows.get(item_id)
        return self._decorate(row, None) if row and row.vault_id == vault_id else None

    async def get_visible(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ContentRecord | None:
        row = self.rows.get(item_id)
        if row and (row.vault_id == vault_id or row.visibility == "public"):
            return self._decorate(row, None)
        return None

    async def update(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, *, data: dict[str, Any], visibility: str
    ) -> ContentRecord | None:
        row = self.rows.get(item_id)
        if row is None or row.vault_id != vault_id:
            return None
        self.rows[item_id] = replace(row, data=copy.deepcopy(data), visibility=visibility, updated_at=self._store.now())
        return self._decorate(self.rows[item_id], None)

    async def set_asset(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, asset_id: uuid.UUID | None
    ) -> ContentRecord | None:
        row = self.rows.get(item_id)
        if row is None or row.vault_id != vault_id:
            return None
        self.rows[item_id] = replace(row, asset_id=asset_id, updated_at=self._store.now())
        return self._decorate(self.rows[item_id], None)

    async def set_judge_score(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, judge_score: dict[str, Any] | None
    ) -> ContentRecord | None:
        row = self.rows.get(item_id)
        if row is None or row.vault_id != vault_id:
            return None
        self.rows[item_id] = replace(
            row,
            judge_score=copy.deepcopy(judge_score) if judge_score is not None else None,
            updated_at=self._store.now(),
        )
        return self._decorate(self.rows[item_id], None)

    async def delete(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        row = self.rows.get(item_id)
        if row is None or row.vault_id != vault_id:
            return False
        del self.rows[item_id]
        return True

    @staticmethod
    def _matches(row: ContentRecord, q: str | None, tag: str | None) -> bool:
        if q and q.strip():
            needle = q.strip().lower()
            haystack = f"{row.data.get('name', '')}\n{row.data.get('tagline', '')}".lower()
            if needle not in haystack:
                return False
        return not tag or tag.lower() in row.data.get("tags", [])

    async def list_owned(
        self, vault_id: uuid.UUID, *, q: str | None, tag: str | None, limit: int, cursor: Cursor | None
    ) -> list[ContentRecord]:
        rows = [self._decorate(r, None) for r in self.rows.values() if r.vault_id == vault_id]
        rows = [r for r in rows if self._matches(r, q, tag)]
        rows.sort(key=lambda r: (r.updated_at, r.id), reverse=True)
        if cursor:
            rows = [r for r in rows if (r.updated_at, r.id) < (cursor.updated_at, cursor.item_id)]
        return rows[: limit + 1]

    async def list_public(
        self,
        viewer_id: uuid.UUID,
        *,
        q: str | None,
        tag: str | None,
        sort: Sort,
        limit: int,
        cursor: Cursor | None,
    ) -> list[ContentRecord]:
        rows = [self._decorate(r, viewer_id) for r in self.rows.values() if r.visibility == "public"]
        rows = [r for r in rows if self._matches(r, q, tag)]
        if sort == "favorites":
            rows.sort(key=lambda r: (r.favorite_count, r.updated_at, r.id), reverse=True)
            if cursor and cursor.count is not None:
                key = (cursor.count, cursor.updated_at, cursor.item_id)
                rows = [r for r in rows if (r.favorite_count, r.updated_at, r.id) < key]
        else:
            rows.sort(key=lambda r: (r.updated_at, r.id), reverse=True)
            if cursor:
                rows = [r for r in rows if (r.updated_at, r.id) < (cursor.updated_at, cursor.item_id)]
        return rows[: limit + 1]

    async def get_many_visible(self, vault_id: uuid.UUID, item_ids: list[uuid.UUID]) -> list[ContentRecord]:
        return [
            self._decorate(r, vault_id)
            for r in self.rows.values()
            if r.id in item_ids and (r.vault_id == vault_id or r.visibility == "public")
        ]

    async def commit(self) -> None:
        return None


@dataclass
class FakePersonaRepository:
    store: FakeStore

    def __post_init__(self) -> None:
        self.rows: dict[uuid.UUID, PersonaRecord] = {}

    async def list(self, vault_id: uuid.UUID) -> list[PersonaRecord]:
        rows = [r for r in self.rows.values() if r.vault_id == vault_id]
        return sorted(rows, key=lambda r: (r.updated_at, r.id), reverse=True)

    async def create(self, vault_id: uuid.UUID, *, data: dict[str, Any]) -> PersonaRecord:
        now = self.store.now()
        row = PersonaRecord(uuid.uuid4(), vault_id, copy.deepcopy(data), None, now, now)
        self.rows[row.id] = row
        return row

    async def get(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> PersonaRecord | None:
        row = self.rows.get(persona_id)
        return row if row and row.vault_id == vault_id else None

    async def update(self, vault_id: uuid.UUID, persona_id: uuid.UUID, *, data: dict[str, Any]) -> PersonaRecord | None:
        row = await self.get(vault_id, persona_id)
        if row is None:
            return None
        self.rows[persona_id] = replace(row, data=copy.deepcopy(data), updated_at=self.store.now())
        return self.rows[persona_id]

    async def set_asset(
        self, vault_id: uuid.UUID, persona_id: uuid.UUID, asset_id: uuid.UUID | None
    ) -> PersonaRecord | None:
        row = await self.get(vault_id, persona_id)
        if row is None:
            return None
        self.rows[persona_id] = replace(row, asset_id=asset_id, updated_at=self.store.now())
        return self.rows[persona_id]

    async def delete(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> bool:
        if await self.get(vault_id, persona_id) is None:
            return False
        del self.rows[persona_id]
        return True

    async def commit(self) -> None:
        return None


class FakeLorebookRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store
        self.rows = store.lorebooks

    def _view(self, row: LorebookRecord, with_entries: bool) -> LorebookRecord:
        return replace(
            row,
            author=self._store.author(row.vault_id),
            entry_count=len(row.entries),
            entries=copy.deepcopy(row.entries) if with_entries else [],
        )

    async def create(
        self,
        vault_id: uuid.UUID,
        *,
        name: str,
        visibility: str,
        settings: dict[str, Any],
        entries: list[dict[str, Any]],
    ) -> LorebookRecord:
        now = self._store.now()
        row = LorebookRecord(
            uuid.uuid4(), vault_id, visibility, name, copy.deepcopy(settings), now, now, "", 0, copy.deepcopy(entries)
        )
        self.rows[row.id] = row
        return self._view(row, True)

    async def get_visible(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> LorebookRecord | None:
        row = self.rows.get(lorebook_id)
        if row and (row.vault_id == vault_id or row.visibility == "public"):
            return self._view(row, True)
        return None

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
        row = self.rows.get(lorebook_id)
        if row is None or row.vault_id != vault_id:
            return None
        self.rows[lorebook_id] = replace(
            row,
            name=name,
            visibility=visibility,
            settings=copy.deepcopy(settings),
            entries=copy.deepcopy(entries),
            updated_at=self._store.now(),
        )
        return self._view(self.rows[lorebook_id], True)

    async def delete(self, vault_id: uuid.UUID, lorebook_id: uuid.UUID) -> bool:
        row = self.rows.get(lorebook_id)
        if row is None or row.vault_id != vault_id:
            return False
        del self.rows[lorebook_id]
        self._store.links = {link for link in self._store.links if link[3] != lorebook_id}
        return True

    async def list_owned(
        self, vault_id: uuid.UUID, *, q: str | None, limit: int, cursor: Cursor | None
    ) -> list[LorebookRecord]:
        rows = [r for r in self.rows.values() if r.vault_id == vault_id]
        if q and q.strip():
            rows = [r for r in rows if q.strip().lower() in r.name.lower()]
        rows.sort(key=lambda r: (r.updated_at, r.id), reverse=True)
        if cursor:
            rows = [r for r in rows if (r.updated_at, r.id) < (cursor.updated_at, cursor.item_id)]
        return [self._view(r, False) for r in rows[: limit + 1]]

    async def visible_ids(self, vault_id: uuid.UUID, lorebook_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return {
            i
            for i in lorebook_ids
            if (row := self.rows.get(i)) and (row.vault_id == vault_id or row.visibility == "public")
        }

    async def sync_links(
        self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID, lorebook_ids: list[uuid.UUID]
    ) -> None:
        kept = {
            link
            for link in self._store.links
            if not (link[0] == vault_id and link[1] == target_type and link[2] == target_id)
        }
        kept |= {(vault_id, target_type, target_id, i) for i in lorebook_ids}
        self._store.links = kept

    async def delete_links_for_target(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> None:
        await self.sync_links(vault_id, target_type, target_id, [])

    async def commit(self) -> None:
        return None


class FakeFavoriteRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def list_targets(self, vault_id: uuid.UUID) -> list[tuple[str, uuid.UUID]]:
        return [(t, i) for v, t, i in reversed(self._store.favorites) if v == vault_id]

    async def add(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> None:
        if (vault_id, target_type, target_id) not in self._store.favorites:
            self._store.favorites.append((vault_id, target_type, target_id))

    async def remove(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> bool:
        key = (vault_id, target_type, target_id)
        if key in self._store.favorites:
            self._store.favorites.remove(key)
            return True
        return False

    async def delete_for_target(self, target_type: str, target_id: uuid.UUID) -> None:
        self._store.favorites = [f for f in self._store.favorites if not (f[1] == target_type and f[2] == target_id)]

    async def commit(self) -> None:
        return None


class FakeAssetRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store

    async def create(self, vault_id: uuid.UUID, *, kind: str, mime: str, data: bytes) -> AssetRecord:
        record = AssetRecord(uuid.uuid4(), vault_id, kind, mime, len(data), data)
        self._store.assets[record.id] = record
        return record

    async def get(self, asset_id: uuid.UUID) -> AssetRecord | None:
        return self._store.assets.get(asset_id)

    async def is_public(self, asset_id: uuid.UUID) -> bool:
        return any(
            row.asset_id == asset_id and row.visibility == "public"
            for rows in self._store.content.values()
            for row in rows.values()
        )

    async def delete(self, vault_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        asset = self._store.assets.get(asset_id)
        if asset and asset.vault_id == vault_id:
            del self._store.assets[asset_id]

    async def commit(self) -> None:
        return None


class FakeCreatorRepository:
    def __init__(self, store: FakeStore) -> None:
        self._store = store
        self.rows = store.creator_sessions

    async def create(self, vault_id: uuid.UUID, *, mode: str, seed: dict[str, Any]) -> CreatorSessionRecord:
        now = self._store.now()
        row = CreatorSessionRecord(
            id=uuid.uuid4(),
            vault_id=vault_id,
            mode=mode,
            seed=copy.deepcopy(seed),
            messages=[],
            raw=None,
            result=None,
            created_at=now,
            updated_at=now,
        )
        self.rows[row.id] = row
        return row

    async def get(self, vault_id: uuid.UUID, session_id: uuid.UUID) -> CreatorSessionRecord | None:
        row = self.rows.get(session_id)
        if row is None or row.vault_id != vault_id:
            return None
        return row

    async def update(
        self, vault_id: uuid.UUID, session_id: uuid.UUID, fields: dict[str, Any]
    ) -> CreatorSessionRecord | None:
        row = self.rows.get(session_id)
        if row is None or row.vault_id != vault_id:
            return None
        updates: dict[str, Any] = {"updated_at": self._store.now()}
        for key, value in fields.items():
            if key not in UPDATABLE_FIELDS:
                raise ValueError(f"cannot update creator session field {key!r}")
            updates[key] = copy.deepcopy(value)
        self.rows[session_id] = replace(row, **updates)
        return self.rows[session_id]

    async def delete(self, vault_id: uuid.UUID, session_id: uuid.UUID) -> bool:
        row = self.rows.get(session_id)
        if row is None or row.vault_id != vault_id:
            return False
        del self.rows[session_id]
        return True

    async def commit(self) -> None:
        return None


def make_fake_repos(store: FakeStore) -> Repos:
    return Repos(
        characters=FakeContentRepository(store, "character"),
        worlds=FakeContentRepository(store, "world"),
        personas=FakePersonaRepository(store),
        lorebooks=FakeLorebookRepository(store),
        favorites=FakeFavoriteRepository(store),
        assets=FakeAssetRepository(store),
    )
