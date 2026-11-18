"""Image assets: upload validation and read access."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.core.config import MAX_IMAGE_BYTES
from app.core.deps import SessionDep
from app.core.errors import AppError
from app.repositories.assets_repo import AssetRecord, AssetRepository, SqlAssetRepository

# Browsers may cache an asset for a day; it is private because access depends on the vault.
ASSET_CACHE_CONTROL = "private, max-age=86400"

_RIFF_HEADER_SIZE = 12
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def sniff_image_mime(content: bytes) -> str | None:
    """Detect png/jpeg/webp from magic bytes; the client-declared content type is never trusted."""
    if content.startswith(_PNG_MAGIC):
        return "image/png"
    if content.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if len(content) >= _RIFF_HEADER_SIZE and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def checked_image(content: bytes) -> str:
    """Return the sniffed mime or raise the contract errors (413 / 415)."""
    if len(content) > MAX_IMAGE_BYTES:
        raise AppError("file_too_large", "Image exceeds the size limit", 413)
    mime = sniff_image_mime(content)
    if mime is None:
        raise AppError("unsupported_media", "Only png, jpeg and webp images are supported", 415)
    return mime


def asset_url(asset_id: uuid.UUID | None) -> str | None:
    return f"/api/assets/{asset_id}" if asset_id else None


@dataclass(frozen=True, slots=True)
class AssetFile:
    content: bytes
    mime: str


class AssetService:
    def __init__(self, assets: AssetRepository) -> None:
        self._assets = assets

    async def read(self, vault_id: uuid.UUID, asset_id: uuid.UUID) -> AssetFile:
        """Bytes of an asset the vault owns or that is the image of a public item; else 404."""
        asset = await self._assets.get(asset_id)
        if asset is None or not await self._can_read(vault_id, asset):
            raise AppError("not_found", "Asset not found", 404)
        return AssetFile(asset.data, asset.mime)

    async def _can_read(self, vault_id: uuid.UUID, asset: AssetRecord) -> bool:
        return asset.vault_id == vault_id or await self._assets.is_public(asset.id)


def get_asset_repo(db: SessionDep) -> AssetRepository:
    return SqlAssetRepository(db)


def get_asset_service(assets: Annotated[AssetRepository, Depends(get_asset_repo)]) -> AssetService:
    return AssetService(assets)


AssetServiceDep = Annotated[AssetService, Depends(get_asset_service)]
