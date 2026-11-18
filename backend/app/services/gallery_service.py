"""Gallery (public items of all vaults) and favorites."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends

from app.core.errors import AppError
from app.repositories.characters_repo import ContentRecord, Cursor, Sort
from app.schemas.library import GalleryItem, TargetType
from app.services.asset_service import asset_url
from app.services.library_service import (
    ContentManager,
    LibraryService,
    get_library_service,
    paginate,
    parse_cursor,
)


class GalleryService:
    def __init__(self, library: LibraryService) -> None:
        self._library = library
        self._favorites = library.repos.favorites

    @staticmethod
    def _item(manager: ContentManager, record: ContentRecord, vault_id: uuid.UUID) -> GalleryItem:
        data = record.data
        return GalleryItem(
            type=manager.kind.target_type,
            id=str(record.id),
            name=data.get("name", ""),
            tagline=manager.kind.tagline(data),
            tags=data.get("tags", []),
            image_url=asset_url(record.asset_id),
            author=record.author,
            is_owner=record.vault_id == vault_id,
            is_favorite=record.is_favorite,
            favorite_count=record.favorite_count,
            updated_at=record.updated_at,
        )

    async def list_items(
        self,
        vault_id: uuid.UUID,
        *,
        target_type: TargetType,
        q: str | None,
        tag: str | None,
        sort: Sort,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[GalleryItem], str | None]:
        manager = self._library.content(target_type)
        position = parse_cursor(cursor)
        if sort == "favorites" and position is not None and position.count is None:
            # A recent-sort cursor has no favorite count; using it here would restart the page forever.
            raise AppError("invalid_cursor", "Cursor is invalid", 422)
        rows = await manager.repo.list_public(vault_id, q=q, tag=tag, sort=sort, limit=limit, cursor=position)

        def make_cursor(r: ContentRecord) -> Cursor:
            return Cursor(r.updated_at, r.id, r.favorite_count if sort == "favorites" else None)

        kept, next_cursor = paginate(rows, limit, make_cursor)
        return [self._item(manager, r, vault_id) for r in kept], next_cursor

    async def favorites(self, vault_id: uuid.UUID) -> list[GalleryItem]:
        targets = await self._favorites.list_targets(vault_id)
        items: list[GalleryItem] = []
        for target_type in ("character", "world"):
            ids = [tid for ttype, tid in targets if ttype == target_type]
            manager = self._library.content(target_type)
            by_id = {r.id: r for r in await manager.repo.get_many_visible(vault_id, ids)}
            items.extend(self._item(manager, by_id[tid], vault_id) for tid in ids if tid in by_id)
        order = {tid: index for index, (_, tid) in enumerate(targets)}
        return sorted(items, key=lambda item: order[uuid.UUID(item.id)])

    async def add_favorite(self, vault_id: uuid.UUID, target_type: TargetType, target_id: uuid.UUID) -> None:
        await self._library.content(target_type).get_record(vault_id, target_id)  # 404 unless visible
        await self._favorites.add(vault_id, target_type, target_id)
        await self._library.repos.commit()

    async def remove_favorite(self, vault_id: uuid.UUID, target_type: TargetType, target_id: uuid.UUID) -> None:
        removed = await self._favorites.remove(vault_id, target_type, target_id)
        if not removed:
            await self._library.content(target_type).get_record(vault_id, target_id)  # 404 unless visible
        await self._library.repos.commit()


def get_gallery_service(library: Annotated[LibraryService, Depends(get_library_service)]) -> GalleryService:
    return GalleryService(library)


GalleryServiceDep = Annotated[GalleryService, Depends(get_gallery_service)]


__all__ = ["GalleryService", "GalleryServiceDep", "get_gallery_service"]
