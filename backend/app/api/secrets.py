"""Secret endpoints. Values are write-only: responses carry `is_set` and a short hint, never the value."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.deps import VaultSessionDep
from app.repositories.secrets_repo import SecretRecord
from app.schemas.vault import SecretListResponse, SecretOut, SecretResponse, SecretValueIn
from app.services.vault_service import VaultServiceDep

router = APIRouter(prefix="/api/secrets", tags=["secrets"])


def _secret_out(name: str, record: SecretRecord | None) -> SecretOut:
    if record is None:
        return SecretOut(name=name, is_set=False)
    return SecretOut(name=name, is_set=True, hint=record.hint, updated_at=record.updated_at)


@router.get("", response_model=SecretListResponse)
async def list_secrets(session: VaultSessionDep, service: VaultServiceDep) -> SecretListResponse:
    entries = await service.list_secrets(session)
    return SecretListResponse(secrets=[_secret_out(name, record) for name, record in entries])


@router.put("/{name}", response_model=SecretResponse)
async def put_secret(
    name: str, body: SecretValueIn, session: VaultSessionDep, service: VaultServiceDep
) -> SecretResponse:
    record = await service.set_secret(session, name, body.value)
    return SecretResponse(secret=_secret_out(name, record))


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(name: str, session: VaultSessionDep, service: VaultServiceDep) -> Response:
    await service.delete_secret(session, name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
