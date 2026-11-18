"""Persona persistence. Every method takes `vault_id` and filters on it."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import Persona


@dataclass(frozen=True, slots=True)
class PersonaRecord:
    id: uuid.UUID
    vault_id: uuid.UUID
    data: dict[str, Any]
    asset_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PersonaRepository(Protocol):
    async def list(self, vault_id: uuid.UUID) -> list[PersonaRecord]: ...

    async def create(self, vault_id: uuid.UUID, *, data: dict[str, Any]) -> PersonaRecord: ...

    async def get(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> PersonaRecord | None: ...

    async def update(
        self, vault_id: uuid.UUID, persona_id: uuid.UUID, *, data: dict[str, Any]
    ) -> PersonaRecord | None: ...

    async def set_asset(
        self, vault_id: uuid.UUID, persona_id: uuid.UUID, asset_id: uuid.UUID | None
    ) -> PersonaRecord | None: ...

    async def delete(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> bool: ...

    async def commit(self) -> None: ...


def _to_record(row: Persona) -> PersonaRecord:
    return PersonaRecord(
        id=row.id,
        vault_id=row.vault_id,
        data=row.data,
        asset_id=row.avatar_asset_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlPersonaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _row(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> Persona | None:
        return await self._session.scalar(select(Persona).where(Persona.id == persona_id, Persona.vault_id == vault_id))

    async def list(self, vault_id: uuid.UUID) -> list[PersonaRecord]:
        rows = await self._session.scalars(
            select(Persona).where(Persona.vault_id == vault_id).order_by(Persona.updated_at.desc(), Persona.id.desc())
        )
        return [_to_record(row) for row in rows]

    async def create(self, vault_id: uuid.UUID, *, data: dict[str, Any]) -> PersonaRecord:
        now = datetime.now(UTC)
        row = Persona(id=uuid.uuid4(), vault_id=vault_id, data=data, created_at=now, updated_at=now)
        self._session.add(row)
        await self._session.flush()
        return _to_record(row)

    async def get(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> PersonaRecord | None:
        row = await self._row(vault_id, persona_id)
        return _to_record(row) if row else None

    async def update(self, vault_id: uuid.UUID, persona_id: uuid.UUID, *, data: dict[str, Any]) -> PersonaRecord | None:
        row = await self._row(vault_id, persona_id)
        if row is None:
            return None
        row.data = data
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_record(row)

    async def set_asset(
        self, vault_id: uuid.UUID, persona_id: uuid.UUID, asset_id: uuid.UUID | None
    ) -> PersonaRecord | None:
        row = await self._row(vault_id, persona_id)
        if row is None:
            return None
        row.avatar_asset_id = asset_id
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _to_record(row)

    async def delete(self, vault_id: uuid.UUID, persona_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(Persona).where(Persona.id == persona_id, Persona.vault_id == vault_id).returning(Persona.id)
        )
        return result.first() is not None

    async def commit(self) -> None:
        await self._session.commit()
