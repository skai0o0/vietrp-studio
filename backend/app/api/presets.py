"""Prompt preset routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.deps import VaultSessionDep
from app.schemas.presets import AgentId, PresetIn, PresetOut
from app.services.preset_service import PresetServiceDep

router = APIRouter(prefix="/api/presets", tags=["presets"])


@router.get("", response_model=list[PresetOut])
async def list_presets(
    session: VaultSessionDep, service: PresetServiceDep, agent: AgentId | None = None
) -> list[PresetOut]:
    return await service.list_presets(session.vault_id, agent)


@router.post("", response_model=PresetOut, status_code=status.HTTP_201_CREATED)
async def create_preset(body: PresetIn, session: VaultSessionDep, service: PresetServiceDep) -> PresetOut:
    return await service.create(session.vault_id, body)


@router.get("/{preset_id}", response_model=PresetOut)
async def get_preset(preset_id: str, session: VaultSessionDep, service: PresetServiceDep) -> PresetOut:
    return await service.get(session.vault_id, preset_id)


@router.put("/{preset_id}", response_model=PresetOut)
async def update_preset(
    preset_id: str, body: PresetIn, session: VaultSessionDep, service: PresetServiceDep
) -> PresetOut:
    return await service.update(session.vault_id, preset_id, body)


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(preset_id: str, session: VaultSessionDep, service: PresetServiceDep) -> Response:
    await service.remove(session.vault_id, preset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
