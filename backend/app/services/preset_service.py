"""Prompt preset use cases. Presets are per vault; another vault's preset is a 404."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends

from app.core.errors import AppError
from app.repositories.presets_repo import PresetRecord
from app.schemas.presets import AgentId, PresetIn, PresetOut
from app.services.chat_service import UnitOfWork, UnitOfWorkDep


def _out(record: PresetRecord) -> PresetOut:
    return PresetOut(
        id=str(record.id),
        agent=record.agent,
        name=record.name,
        layers=record.layers,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _not_found() -> AppError:
    return AppError("not_found", "Preset not found", 404)


def _parse(preset_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(preset_id)
    except ValueError as exc:
        raise _not_found() from exc


class PresetService:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def list_presets(self, vault_id: uuid.UUID, agent: AgentId | None) -> list[PresetOut]:
        async with self._uow() as r:
            return [_out(p) for p in await r.presets.list_presets(vault_id, agent=agent)]

    async def get(self, vault_id: uuid.UUID, preset_id: str) -> PresetOut:
        async with self._uow() as r:
            record = await r.presets.get(vault_id, _parse(preset_id))
        if record is None:
            raise _not_found()
        return _out(record)

    async def create(self, vault_id: uuid.UUID, body: PresetIn) -> PresetOut:
        async with self._uow() as r:
            record = await r.presets.create(vault_id, agent=body.agent, name=body.name, layers=body.layers)
            await r.commit()
        return _out(record)

    async def update(self, vault_id: uuid.UUID, preset_id: str, body: PresetIn) -> PresetOut:
        async with self._uow() as r:
            record = await r.presets.update(
                vault_id, _parse(preset_id), agent=body.agent, name=body.name, layers=body.layers
            )
            if record is None:
                raise _not_found()
            await r.commit()
        return _out(record)

    async def remove(self, vault_id: uuid.UUID, preset_id: str) -> None:
        async with self._uow() as r:
            if not await r.presets.delete(vault_id, _parse(preset_id)):
                raise _not_found()
            await r.commit()


def get_preset_service(uow: UnitOfWorkDep) -> PresetService:
    return PresetService(uow)


PresetServiceDep = Annotated[PresetService, Depends(get_preset_service)]
