"""Asset download route."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from app.core.deps import VaultSessionDep
from app.services.asset_service import ASSET_CACHE_CONTROL, AssetServiceDep

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/{asset_id}")
async def get_asset(asset_id: uuid.UUID, session: VaultSessionDep, service: AssetServiceDep) -> Response:
    asset = await service.read(session.vault_id, asset_id)
    return Response(asset.content, media_type=asset.mime, headers={"Cache-Control": ASSET_CACHE_CONTROL})
