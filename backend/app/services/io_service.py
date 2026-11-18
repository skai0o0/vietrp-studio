"""Import and export of characters, worlds and lorebooks through the WP-H format functions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Literal

import anyio
from fastapi import Depends

from app.core.config import MAX_IMAGE_BYTES, MAX_IMPORT_BYTES
from app.core.errors import AppError
from app.formats.common import FormatWarning
from app.formats.png import is_png, strip_text_chunks
from app.formats.st_export import export_character, export_lorebook, export_world
from app.formats.st_import import ImportResult, import_file
from app.schemas.library import CharacterOut, ImportResponse, LorebookOut, WorldOut
from app.services.asset_service import sniff_image_mime
from app.services.library_service import LibraryService, get_library_service

ALLOWED_IMPORT_SUFFIXES = (".json", ".png")
PNG_MIME = "image/png"


@dataclass(frozen=True, slots=True)
class ExportFile:
    body: bytes
    mime: str
    filename: str


def _unique_id(entry_id: str, used: set[str]) -> str:
    candidate, n = entry_id, 1
    while candidate in used:
        n += 1
        candidate = f"{entry_id[:36]}_{n}"
    used.add(candidate)
    return candidate


class IoService:
    def __init__(self, library: LibraryService) -> None:
        self._library = library
        self._repos = library.repos

    # --- import ---

    async def import_upload(self, vault_id: uuid.UUID, filename: str, content: bytes) -> ImportResponse:
        if len(content) > MAX_IMPORT_BYTES:
            raise AppError("file_too_large", "File exceeds the size limit", 413)
        if not filename.lower().endswith(ALLOWED_IMPORT_SUFFIXES):
            raise AppError("unsupported_media", "Only .json and .png files can be imported", 415)
        # Parsing (PNG chunks, base64, JSON) is CPU work: keep it off the event loop.
        result: ImportResult = await anyio.to_thread.run_sync(import_file, content, filename)
        warnings = [FormatWarning.model_validate(w, from_attributes=True) for w in result.warnings]

        if result.kind == "lorebook":
            book = await self._library.lorebooks.create(vault_id, result.data, "private", commit=False)
            await self._repos.commit()
            return ImportResponse(kind="lorebook", lorebook=book, warnings=warnings, needs_age=False)

        embedded: LorebookOut | None = None
        data = dict(result.data)
        if result.lorebook is not None:
            embedded = await self._library.lorebooks.create(vault_id, result.lorebook, "private", commit=False)
            data["lorebook_ids"] = await self._link_ids(vault_id, data, result.merged_lorebook, embedded.id)

        manager = self._library.content(result.kind)
        image = self._usable_avatar(result, warnings)
        # One transaction for lorebook + card: if the card fails, the session rolls everything back.
        item = await manager.create(vault_id, data, "private", imported=True, image=image, commit=False)
        await self._repos.commit()
        warnings.extend(w for w in item.warnings if (w.path, w.code) not in {(x.path, x.code) for x in warnings})
        # Optional members are left unset (not None) so the route can omit them from the JSON.
        extra: dict[str, Any] = {} if embedded is None else {"lorebook": embedded}
        if isinstance(item, CharacterOut):
            return ImportResponse(
                kind="character", character=item, warnings=warnings, needs_age=result.needs_age, **extra
            )
        assert isinstance(item, WorldOut)
        return ImportResponse(kind="world", world=item, warnings=warnings, needs_age=False, **extra)

    async def _link_ids(self, vault_id: uuid.UUID, data: dict[str, Any], merged: bool, embedded_id: str) -> list[str]:
        """Lorebooks to link on an imported card.

        A VietRP export embeds the merged copy of every linked book, so the original ids are dropped
        (keeping both would inject each entry twice). Otherwise keep the visible original ids.
        """
        if merged:
            return [embedded_id]
        wanted = [uuid.UUID(str(i)) for i in data.get("lorebook_ids", [])]
        visible = await self._repos.lorebooks.visible_ids(vault_id, wanted)
        kept = [str(i) for i in wanted if i in visible]
        return list(dict.fromkeys([*kept, embedded_id]))

    @staticmethod
    def _usable_avatar(result: ImportResult, warnings: list[FormatWarning]) -> bytes | None:
        if result.avatar is None:
            return None
        content = result.avatar[0]
        if len(content) > MAX_IMAGE_BYTES or sniff_image_mime(content) is None:
            warnings.append(FormatWarning(path="avatar", code="avatar_ignored", message="avatar was not stored"))
            return None
        # The original card JSON rides in the PNG text chunks; a public avatar must not leak it.
        return strip_text_chunks(content) if is_png(content) else content

    # --- export ---

    async def _meta(self, record_id: uuid.UUID, author: str, created: Any, updated: Any) -> dict[str, Any]:
        return {
            "id": str(record_id),
            "creator": author,
            "created_at": created.isoformat(),
            "updated_at": updated.isoformat(),
        }

    async def _merged_lorebook(self, vault_id: uuid.UUID, ids: list[Any], name: str) -> dict[str, Any] | None:
        """ST cards hold one character book, so linked lorebooks are merged into one."""
        entries: list[dict[str, Any]] = []
        used: set[str] = set()
        for raw in ids:
            record = await self._repos.lorebooks.get_visible(vault_id, uuid.UUID(str(raw)))
            if record is None:
                continue
            for entry in record.entries:
                entries.append({**entry, "id": _unique_id(entry["id"], used)})
        if not entries:
            return None
        return {"format": "vietrp-lorebook", "spec_version": "1.0", "name": name[:80], "entries": entries}

    async def export_character(
        self,
        vault_id: uuid.UUID,
        item_id: uuid.UUID,
        *,
        fmt: Literal["vietrp", "ccv2", "ccv3"],
        as_: Literal["json", "png"],
    ) -> ExportFile:
        record = await self._library.characters.get_record(vault_id, item_id)
        avatar: bytes | None = None
        if as_ == "png" and record.asset_id:
            asset = await self._repos.assets.get(record.asset_id)
            # Only PNG avatars can carry the card; other formats fall back to the placeholder image.
            if asset is not None and asset.mime == PNG_MIME:
                avatar = asset.data
        lorebook = await self._merged_lorebook(vault_id, record.data.get("lorebook_ids", []), record.data["name"])
        meta = await self._meta(record.id, record.author, record.created_at, record.updated_at)
        body, mime, filename = await anyio.to_thread.run_sync(
            lambda: export_character(record.data, fmt=fmt, as_=as_, avatar=avatar, lorebook=lorebook, meta=meta)
        )
        return ExportFile(body, mime, filename)

    async def export_world(self, vault_id: uuid.UUID, item_id: uuid.UUID) -> ExportFile:
        record = await self._library.worlds.get_record(vault_id, item_id)
        meta = await self._meta(record.id, record.author, record.created_at, record.updated_at)
        body, mime, filename = export_world(record.data, meta=meta)
        return ExportFile(body, mime, filename)

    async def export_lorebook(
        self, vault_id: uuid.UUID, lorebook_id: uuid.UUID, *, fmt: Literal["vietrp", "st"]
    ) -> ExportFile:
        record = await self._library.lorebooks.get_record(vault_id, lorebook_id)
        book = self._library.lorebooks.data_of(record)
        meta = await self._meta(record.id, record.author, record.created_at, record.updated_at)
        body, mime, filename = export_lorebook(book, fmt=fmt, meta=meta)
        return ExportFile(body, mime, filename)


def get_io_service(library: Annotated[LibraryService, Depends(get_library_service)]) -> IoService:
    return IoService(library)


IoServiceDep = Annotated[IoService, Depends(get_io_service)]
