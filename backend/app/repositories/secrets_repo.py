"""Secret persistence. Every method takes `vault_id` and filters on it."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vault import Secret


@dataclass(frozen=True, slots=True)
class SecretRecord:
    name: str
    ciphertext: bytes
    hint: str | None
    updated_at: datetime


class SecretRepository(Protocol):
    async def list(self, vault_id: uuid.UUID) -> list[SecretRecord]: ...

    async def get(self, vault_id: uuid.UUID, name: str) -> SecretRecord | None: ...

    async def upsert(self, vault_id: uuid.UUID, name: str, ciphertext: bytes, hint: str | None) -> SecretRecord: ...

    async def delete(self, vault_id: uuid.UUID, name: str) -> None: ...

    async def commit(self) -> None: ...


def _to_record(row: Secret) -> SecretRecord:
    return SecretRecord(name=row.name, ciphertext=row.ciphertext, hint=row.hint, updated_at=row.updated_at)


class SqlSecretRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, vault_id: uuid.UUID) -> list[SecretRecord]:
        rows = await self._session.scalars(select(Secret).where(Secret.vault_id == vault_id))
        return [_to_record(row) for row in rows]

    async def get(self, vault_id: uuid.UUID, name: str) -> SecretRecord | None:
        row = await self._session.get(Secret, (vault_id, name))
        return _to_record(row) if row else None

    async def upsert(self, vault_id: uuid.UUID, name: str, ciphertext: bytes, hint: str | None) -> SecretRecord:
        now = datetime.now(UTC)
        stmt = insert(Secret).values(vault_id=vault_id, name=name, ciphertext=ciphertext, hint=hint, updated_at=now)
        stmt = stmt.on_conflict_do_update(
            index_elements=[Secret.vault_id, Secret.name],
            set_={"ciphertext": ciphertext, "hint": hint, "updated_at": now},
        )
        await self._session.execute(stmt)
        return SecretRecord(name=name, ciphertext=ciphertext, hint=hint, updated_at=now)

    async def delete(self, vault_id: uuid.UUID, name: str) -> None:
        await self._session.execute(delete(Secret).where(Secret.vault_id == vault_id, Secret.name == name))

    async def commit(self) -> None:
        await self._session.commit()
