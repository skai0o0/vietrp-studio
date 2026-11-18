"""Import route."""

from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api._http import read_upload
from app.core.deps import SettingsDep, VaultSessionDep
from app.schemas.library import ImportResponse
from app.services.io_service import IoServiceDep

router = APIRouter(prefix="/api", tags=["io"])


@router.post(
    "/import", response_model=ImportResponse, response_model_exclude_unset=True, status_code=status.HTTP_201_CREATED
)
async def import_file(
    request: Request, session: VaultSessionDep, service: IoServiceDep, settings: SettingsDep
) -> ImportResponse:
    filename, content = await read_upload(request, settings.max_import_bytes)
    return await service.import_upload(session.vault_id, filename, content)
