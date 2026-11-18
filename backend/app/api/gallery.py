"""Gallery and favorites routes."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status

from app.core.deps import VaultSessionDep
from app.schemas.library import FavoritesResponse, GalleryPage, TargetType
from app.services.gallery_service import GalleryServiceDep

# Same page-size contract as the library lists: default 30, at most 100.
DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100

router = APIRouter(prefix="/api", tags=["gallery"])


@router.get("/gallery", response_model=GalleryPage)
async def list_gallery(
    session: VaultSessionDep,
    service: GalleryServiceDep,
    type_: Annotated[TargetType, Query(alias="type")] = "character",
    q: str | None = None,
    tag: str | None = None,
    sort: Literal["recent", "favorites"] = "recent",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> dict[str, Any]:
    items, next_cursor = await service.list_items(
        session.vault_id, target_type=type_, q=q, tag=tag, sort=sort, limit=limit, cursor=cursor
    )
    return {"items": items, "next_cursor": next_cursor}


@router.get("/favorites", response_model=FavoritesResponse)
async def list_favorites(session: VaultSessionDep, service: GalleryServiceDep) -> dict[str, Any]:
    return {"items": await service.favorites(session.vault_id)}


@router.put("/favorites/{target_type}/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_favorite(
    target_type: TargetType, target_id: uuid.UUID, session: VaultSessionDep, service: GalleryServiceDep
) -> Response:
    await service.add_favorite(session.vault_id, target_type, target_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/favorites/{target_type}/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    target_type: TargetType, target_id: uuid.UUID, session: VaultSessionDep, service: GalleryServiceDep
) -> Response:
    await service.remove_favorite(session.vault_id, target_type, target_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
