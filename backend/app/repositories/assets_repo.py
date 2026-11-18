"""Asset (image) persistence."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.models.library import Asset, Character, World


@dataclass(frozen=True, slots=True)
class AssetRecord:
    id: uuid.UUID
    vault_id: uuid.UUID
    kind: str
    mime: str
    size_bytes: int
    data: bytes


class AssetRepository(Protocol):
    async def create(self, vault_id: uuid.UUID, *, kind: str, mime: str, data: bytes) -> AssetRecord: ...

    async def get(self, asset_id: uuid.UUID) -> AssetRecord | None:
        """Unscoped read. Callers must apply `can_read` rules before exposing the bytes."""
        ...

    async def is_public(self, asset_id: uuid.UUID) -> bool:
        """True when the asset is the image of a public character or world."""
        ...

    async def delete(self, vault_id: uuid.UUID, asset_id: uuid.UUID) -> None: ...

    async def commit(self) -> None: ...


class SqlAssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, vault_id: uuid.UUID, *, kind: str, mime: str, data: bytes) -> AssetRecord:
        asset_id = uuid.uuid4()
        self._session.add(
            Asset(id=asset_id, vault_id=vault_id, kind=kind, mime=mime, data_bytes=data, size_bytes=len(data))
        )
        await self._session.flush()
        return AssetRecord(asset_id, vault_id, kind, mime, len(data), data)

    async def get(self, asset_id: uuid.UUID) -> AssetRecord | None:
        row = await self._session.scalar(select(Asset).options(undefer(Asset.data_bytes)).where(Asset.id == asset_id))
        if row is None:
            return None
        return AssetRecord(row.id, row.vault_id, row.kind, row.mime, row.size_bytes, row.data_bytes or b"")

    async def is_public(self, asset_id: uuid.UUID) -> bool:
        stmt = select(
            or_(
                exists().where(Character.avatar_asset_id == asset_id, Character.visibility == "public"),
                exists().where(World.cover_asset_id == asset_id, World.visibility == "public"),
            )
        )
        return bool(await self._session.scalar(stmt))

    async def delete(self, vault_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        await self._session.execute(delete(Asset).where(Asset.id == asset_id, Asset.vault_id == vault_id))

    async def commit(self) -> None:
        await self._session.commit()
