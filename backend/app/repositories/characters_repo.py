"""Character persistence, plus the record, cursor and SQL base shared with the world repository."""

from __future__ import annotations

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from sqlalchemy import Select, and_, delete, exists, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import Character, Favorite
from app.models.vault import Vault

Sort = Literal["recent", "favorites"]
TargetKind = Literal["character", "world"]


_INT4_LIMIT = 2**31


class InvalidCursorError(ValueError):
    """The pagination cursor is not one we issued."""


@dataclass(frozen=True, slots=True)
class Cursor:
    """Keyset position. `count` is only set for the favorites sort."""

    updated_at: datetime
    item_id: uuid.UUID
    count: int | None = None


def encode_cursor(cursor: Cursor) -> str:
    raw = json.dumps({"u": cursor.updated_at.isoformat(), "i": str(cursor.item_id), "c": cursor.count})
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(value: str) -> Cursor:
    try:
        parsed = json.loads(base64.urlsafe_b64decode(value.encode()))
        count = parsed["c"]
        # Favorite counts are int4 in PostgreSQL; anything outside that range cannot be one we issued.
        if count is not None and (
            isinstance(count, bool) or not isinstance(count, int) or not 0 <= count < _INT4_LIMIT
        ):
            raise ValueError("bad count")
        updated_at = datetime.fromisoformat(parsed["u"])
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return Cursor(updated_at, uuid.UUID(parsed["i"]), count)
    except (binascii.Error, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise InvalidCursorError("invalid cursor") from exc


@dataclass(frozen=True, slots=True)
class ContentRecord:
    """A character or world row joined with its author's display name."""

    id: uuid.UUID
    vault_id: uuid.UUID
    visibility: str
    data: dict[str, Any]
    asset_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    author: str
    favorite_count: int = 0
    is_favorite: bool = False
    judge_score: dict[str, Any] | None = None


class ContentRepository(Protocol):
    """Shared contract of the character and world repositories."""

    async def create(self, vault_id: uuid.UUID, *, data: dict[str, Any], visibility: str) -> ContentRecord: ...

    async def get_owned(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ContentRecord | None: ...

    async def get_visible(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ContentRecord | None:
        """The vault's own item, or any vault's public item."""
        ...

    async def update(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, *, data: dict[str, Any], visibility: str
    ) -> ContentRecord | None: ...

    async def set_asset(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, asset_id: uuid.UUID | None
    ) -> ContentRecord | None: ...

    async def set_judge_score(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, judge_score: dict[str, Any] | None
    ) -> ContentRecord | None: ...

    async def delete(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> bool: ...

    async def list_owned(
        self, vault_id: uuid.UUID, *, q: str | None, tag: str | None, limit: int, cursor: Cursor | None
    ) -> list[ContentRecord]:
        """Up to `limit + 1` rows, newest first (the extra row tells the caller there is a next page)."""
        ...

    async def list_public(
        self,
        viewer_id: uuid.UUID,
        *,
        q: str | None,
        tag: str | None,
        sort: Sort,
        limit: int,
        cursor: Cursor | None,
    ) -> list[ContentRecord]: ...

    async def get_many_visible(self, vault_id: uuid.UUID, item_ids: list[uuid.UUID]) -> list[ContentRecord]:
        """Own or public rows among `item_ids`, with favorite counts for `vault_id`."""
        ...

    async def commit(self) -> None: ...


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlContentRepository:
    """SQL implementation shared by characters and worlds; subclasses set the model and asset column."""

    _model: Any
    _asset_column: str
    _target_type: TargetKind

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- query helpers ---

    def _favorite_count(self) -> Any:
        return (
            select(func.count())
            .select_from(Favorite)
            .where(Favorite.target_type == self._target_type, Favorite.target_id == self._model.id)
            .correlate(self._model)
            .scalar_subquery()
        )

    def _is_favorite(self, viewer_id: uuid.UUID | None) -> Any:
        if viewer_id is None:
            return false()
        return (
            exists()
            .where(
                Favorite.vault_id == viewer_id,
                Favorite.target_type == self._target_type,
                Favorite.target_id == self._model.id,
            )
            .correlate(self._model)
        )

    def _base_select(self, viewer_id: uuid.UUID | None) -> Select[Any]:
        model = self._model
        return select(model, Vault.display_name, self._favorite_count(), self._is_favorite(viewer_id)).join(
            Vault, Vault.id == model.vault_id
        )

    def _filters(self, stmt: Select[Any], q: str | None, tag: str | None) -> Select[Any]:
        model = self._model
        if q and q.strip():
            pattern = f"%{escape_like(q.strip())}%"
            stmt = stmt.where(
                or_(
                    model.data["name"].astext.ilike(pattern, escape="\\"),
                    model.data["tagline"].astext.ilike(pattern, escape="\\"),
                )
            )
        if tag:
            stmt = stmt.where(model.data["tags"].contains([tag.lower()]))
        return stmt

    def _to_record(self, row: Any) -> ContentRecord:
        model, author, favorite_count, is_favorite = row
        return ContentRecord(
            id=model.id,
            vault_id=model.vault_id,
            visibility=model.visibility,
            data=model.data,
            asset_id=getattr(model, self._asset_column),
            created_at=model.created_at,
            updated_at=model.updated_at,
            author=author,
            favorite_count=int(favorite_count),
            is_favorite=bool(is_favorite),
            judge_score=model.judge_score,
        )

    async def _fetch_one(self, *conditions: Any) -> ContentRecord | None:
        result = await self._session.execute(self._base_select(None).where(*conditions))
        row = result.first()
        return self._to_record(row) if row else None

    def _after_recent(self, cursor: Cursor) -> Any:
        model = self._model
        return or_(
            model.updated_at < cursor.updated_at,
            and_(model.updated_at == cursor.updated_at, model.id < cursor.item_id),
        )

    # --- CRUD ---

    async def create(self, vault_id: uuid.UUID, *, data: dict[str, Any], visibility: str) -> ContentRecord:
        now = datetime.now(UTC)
        item_id = uuid.uuid4()
        self._session.add(
            self._model(id=item_id, vault_id=vault_id, data=data, visibility=visibility, created_at=now, updated_at=now)
        )
        await self._session.flush()
        record = await self.get_owned(vault_id, item_id)
        assert record is not None
        return record

    async def get_owned(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ContentRecord | None:
        return await self._fetch_one(self._model.id == item_id, self._model.vault_id == vault_id)

    async def get_visible(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ContentRecord | None:
        model = self._model
        return await self._fetch_one(model.id == item_id, or_(model.vault_id == vault_id, model.visibility == "public"))

    async def _owned_row(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> Any | None:
        return await self._session.scalar(
            select(self._model).where(self._model.id == item_id, self._model.vault_id == vault_id)
        )

    async def update(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, *, data: dict[str, Any], visibility: str
    ) -> ContentRecord | None:
        row = await self._owned_row(vault_id, item_id)
        if row is None:
            return None
        row.data = data
        row.visibility = visibility
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return await self.get_owned(vault_id, item_id)

    async def set_asset(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, asset_id: uuid.UUID | None
    ) -> ContentRecord | None:
        row = await self._owned_row(vault_id, item_id)
        if row is None:
            return None
        setattr(row, self._asset_column, asset_id)
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return await self.get_owned(vault_id, item_id)

    async def set_judge_score(
        self, vault_id: uuid.UUID, item_id: uuid.UUID, judge_score: dict[str, Any] | None
    ) -> ContentRecord | None:
        row = await self._owned_row(vault_id, item_id)
        if row is None:
            return None
        row.judge_score = judge_score
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return await self.get_owned(vault_id, item_id)

    async def delete(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> bool:
        model = self._model
        result = await self._session.execute(
            delete(model).where(model.id == item_id, model.vault_id == vault_id).returning(model.id)
        )
        return result.first() is not None

    # --- listings ---

    async def list_owned(
        self, vault_id: uuid.UUID, *, q: str | None, tag: str | None, limit: int, cursor: Cursor | None
    ) -> list[ContentRecord]:
        model = self._model
        stmt = self._filters(self._base_select(None).where(model.vault_id == vault_id), q, tag)
        if cursor:
            stmt = stmt.where(self._after_recent(cursor))
        stmt = stmt.order_by(model.updated_at.desc(), model.id.desc()).limit(limit + 1)
        return [self._to_record(row) for row in (await self._session.execute(stmt)).all()]

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
        model = self._model
        count = self._favorite_count()
        stmt = self._filters(self._base_select(viewer_id).where(model.visibility == "public"), q, tag)
        if sort == "favorites":
            if cursor and cursor.count is not None:
                stmt = stmt.where(
                    or_(
                        count < cursor.count,
                        and_(count == cursor.count, model.updated_at < cursor.updated_at),
                        and_(count == cursor.count, model.updated_at == cursor.updated_at, model.id < cursor.item_id),
                    )
                )
            stmt = stmt.order_by(count.desc(), model.updated_at.desc(), model.id.desc())
        else:
            if cursor:
                stmt = stmt.where(self._after_recent(cursor))
            stmt = stmt.order_by(model.updated_at.desc(), model.id.desc())
        return [self._to_record(row) for row in (await self._session.execute(stmt.limit(limit + 1))).all()]

    async def get_many_visible(self, vault_id: uuid.UUID, item_ids: list[uuid.UUID]) -> list[ContentRecord]:
        if not item_ids:
            return []
        model = self._model
        stmt = self._base_select(vault_id).where(
            model.id.in_(item_ids), or_(model.vault_id == vault_id, model.visibility == "public")
        )
        return [self._to_record(row) for row in (await self._session.execute(stmt)).all()]

    async def commit(self) -> None:
        await self._session.commit()


class SqlCharacterRepository(SqlContentRepository):
    _model = Character
    _asset_column = "avatar_asset_id"
    _target_type: TargetKind = "character"
