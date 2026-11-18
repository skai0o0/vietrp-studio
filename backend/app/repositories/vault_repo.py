"""Vault persistence: the repository protocol and its SQLAlchemy implementation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vault import Vault


class DuplicateVaultError(Exception):
    """A vault with this lookup hash already exists."""


@dataclass(frozen=True, slots=True)
class VaultRecord:
    id: uuid.UUID
    lookup_hash: bytes
    kdf_salt: bytes
    wrapped_dek: bytes
    display_name: str
    created_at: datetime
    last_seen_at: datetime


class VaultRepository(Protocol):
    async def find_by_lookup(self, lookup_hash: bytes) -> VaultRecord | None: ...

    async def get(self, vault_id: uuid.UUID) -> VaultRecord | None: ...

    async def create(
        self, *, lookup_hash: bytes, kdf_salt: bytes, wrapped_dek: bytes, display_name: str
    ) -> VaultRecord: ...

    async def rename(self, vault_id: uuid.UUID, display_name: str) -> VaultRecord | None: ...

    async def touch(self, vault_id: uuid.UUID) -> None: ...

    async def commit(self) -> None: ...


def _to_record(row: Vault) -> VaultRecord:
    return VaultRecord(
        id=row.id,
        lookup_hash=row.lookup_hash,
        kdf_salt=row.kdf_salt,
        wrapped_dek=row.wrapped_dek,
        display_name=row.display_name,
        created_at=row.created_at,
        last_seen_at=row.last_seen_at,
    )


class SqlVaultRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_lookup(self, lookup_hash: bytes) -> VaultRecord | None:
        row = await self._session.scalar(select(Vault).where(Vault.lookup_hash == lookup_hash))
        return _to_record(row) if row else None

    async def get(self, vault_id: uuid.UUID) -> VaultRecord | None:
        row = await self._session.get(Vault, vault_id)
        return _to_record(row) if row else None

    async def create(
        self, *, lookup_hash: bytes, kdf_salt: bytes, wrapped_dek: bytes, display_name: str
    ) -> VaultRecord:
        row = Vault(
            lookup_hash=lookup_hash,
            kdf_salt=kdf_salt,
            wrapped_dek=wrapped_dek,
            display_name=display_name,
        )
        self._session.add(row)
        try:
            await self._session.flush()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateVaultError from exc
        await self._session.refresh(row)
        return _to_record(row)

    async def rename(self, vault_id: uuid.UUID, display_name: str) -> VaultRecord | None:
        row = await self._session.get(Vault, vault_id)
        if row is None:
            return None
        row.display_name = display_name
        await self._session.flush()
        return _to_record(row)

    async def touch(self, vault_id: uuid.UUID) -> None:
        await self._session.execute(update(Vault).where(Vault.id == vault_id).values(last_seen_at=datetime.now(UTC)))

    async def commit(self) -> None:
        await self._session.commit()
