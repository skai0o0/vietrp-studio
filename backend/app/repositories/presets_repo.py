"""Prompt preset persistence. Every method takes `vault_id` and filters on it."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.library import PromptPreset


@dataclass(frozen=True, slots=True)
class PresetRecord:
    id: uuid.UUID
    vault_id: uuid.UUID
    agent: str
    name: str
    layers: dict[str, str]
    created_at: datetime
    updated_at: datetime


class PresetRepository(Protocol):
    async def list_presets(self, vault_id: uuid.UUID, *, agent: str | None) -> list[PresetRecord]:
        """Most recently updated first."""
        ...

    async def get(self, vault_id: uuid.UUID, preset_id: uuid.UUID) -> PresetRecord | None: ...

    async def create(self, vault_id: uuid.UUID, *, agent: str, name: str, layers: dict[str, str]) -> PresetRecord: ...

    async def update(
        self, vault_id: uuid.UUID, preset_id: uuid.UUID, *, agent: str, name: str, layers: dict[str, str]
    ) -> PresetRecord | None: ...

    async def delete(self, vault_id: uuid.UUID, preset_id: uuid.UUID) -> bool: ...


def _record(row: PromptPreset) -> PresetRecord:
    layers = {k: v for k, v in row.layers.items() if isinstance(v, str)}
    return PresetRecord(row.id, row.vault_id, row.agent, row.name, layers, row.created_at, row.updated_at)


class SqlPresetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _row(self, vault_id: uuid.UUID, preset_id: uuid.UUID) -> PromptPreset | None:
        return await self._session.scalar(
            select(PromptPreset).where(PromptPreset.id == preset_id, PromptPreset.vault_id == vault_id)
        )

    async def list_presets(self, vault_id: uuid.UUID, *, agent: str | None) -> list[PresetRecord]:
        query = select(PromptPreset).where(PromptPreset.vault_id == vault_id)
        if agent is not None:
            query = query.where(PromptPreset.agent == agent)
        rows = await self._session.scalars(query.order_by(PromptPreset.updated_at.desc(), PromptPreset.id.desc()))
        return [_record(r) for r in rows]

    async def get(self, vault_id: uuid.UUID, preset_id: uuid.UUID) -> PresetRecord | None:
        row = await self._row(vault_id, preset_id)
        return _record(row) if row else None

    async def create(self, vault_id: uuid.UUID, *, agent: str, name: str, layers: dict[str, str]) -> PresetRecord:
        now = datetime.now(UTC)
        row = PromptPreset(
            id=uuid.uuid4(), vault_id=vault_id, agent=agent, name=name, layers=layers, created_at=now, updated_at=now
        )
        self._session.add(row)
        await self._session.flush()
        return _record(row)

    async def update(
        self, vault_id: uuid.UUID, preset_id: uuid.UUID, *, agent: str, name: str, layers: dict[str, str]
    ) -> PresetRecord | None:
        row = await self._row(vault_id, preset_id)
        if row is None:
            return None
        row.agent, row.name, row.layers = agent, name, layers
        row.updated_at = datetime.now(UTC)
        await self._session.flush()
        return _record(row)

    async def delete(self, vault_id: uuid.UUID, preset_id: uuid.UUID) -> bool:
        result = await self._session.execute(
            delete(PromptPreset)
            .where(PromptPreset.id == preset_id, PromptPreset.vault_id == vault_id)
            .returning(PromptPreset.id)
        )
        return result.first() is not None
