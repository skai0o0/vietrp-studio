"""Favorite persistence. Reads and writes are scoped to the acting vault."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import Favorite


class FavoriteRepository(Protocol):
    async def list_targets(self, vault_id: uuid.UUID) -> list[tuple[str, uuid.UUID]]:
        """`(target_type, target_id)` pairs, most recently favorited first."""
        ...

    async def add(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> None:
        """Idempotent."""
        ...

    async def remove(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> bool: ...

    async def delete_for_target(self, target_type: str, target_id: uuid.UUID) -> None:
        """Drop every vault's favorites of a deleted item. Only call it for an item the acting vault just deleted."""
        ...

    async def commit(self) -> None: ...


class SqlFavoriteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_targets(self, vault_id: uuid.UUID) -> list[tuple[str, uuid.UUID]]:
        rows = await self._session.execute(
            select(Favorite.target_type, Favorite.target_id)
            .where(Favorite.vault_id == vault_id)
            .order_by(Favorite.created_at.desc(), Favorite.id.desc())
        )
        return [(row[0], row[1]) for row in rows.all()]

    async def add(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> None:
        stmt = (
            insert(Favorite)
            .values(id=uuid.uuid4(), vault_id=vault_id, target_type=target_type, target_id=target_id)
            .on_conflict_do_nothing(index_elements=[Favorite.vault_id, Favorite.target_type, Favorite.target_id])
        )
        await self._session.execute(stmt)

    async def remove(self, vault_id: uuid.UUID, target_type: str, target_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(Favorite)
            .where(
                Favorite.vault_id == vault_id,
                Favorite.target_type == target_type,
                Favorite.target_id == target_id,
            )
            .returning(Favorite.id)
        )
        return result.first() is not None

    async def delete_for_target(self, target_type: str, target_id: uuid.UUID) -> None:
        await self._session.execute(
            delete(Favorite).where(Favorite.target_type == target_type, Favorite.target_id == target_id)
        )

    async def commit(self) -> None:
        await self._session.commit()
