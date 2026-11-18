"""Library routes: characters, worlds, personas and lorebooks of the unlocked vault."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api._http import file_response, read_upload
from app.core.deps import GatewayFactoryDep, SettingsDep, VaultSessionDep
from app.core.errors import AppError
from app.schemas.library import (
    CharacterPage,
    CharacterResponse,
    ItemWrite,
    LorebookPage,
    LorebookResponse,
    PersonaListResponse,
    PersonaResponse,
    PersonaWrite,
    WorldPage,
    WorldResponse,
)
from app.services.io_service import IoServiceDep
from app.services.library_service import ContentManager, LibraryServiceDep
from app.services.turn_service import KeyCheck, get_key_check

# List page size from the API contract (WP-I): default 30, at most 100.
DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100

LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
ExportFormat = Literal["vietrp", "ccv2", "ccv3"]
ExportAs = Literal["json", "png"]

NO_CONTENT = status.HTTP_204_NO_CONTENT


def _build_content_router(
    prefix: str,
    kind: Literal["character", "world"],
    page_model: type[Any],
    response_model: type[Any],
    response_key: str,
) -> APIRouter:
    """Characters and worlds expose the same nine routes; only the models and the export options differ."""
    router = APIRouter(prefix=prefix, tags=[prefix.rsplit("/", 1)[-1]])
    image_name = "avatar" if kind == "character" else "cover"

    def manager(service: LibraryServiceDep) -> ContentManager:
        return service.content(kind)

    def wrap(item: Any) -> dict[str, Any]:
        return {response_key: item}

    @router.get("", response_model=page_model)
    async def list_items(
        session: VaultSessionDep,
        service: LibraryServiceDep,
        q: str | None = None,
        tag: str | None = None,
        limit: LimitQuery = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        items, next_cursor = await manager(service).list_items(
            session.vault_id, q=q, tag=tag, limit=limit, cursor=cursor
        )
        return {"items": items, "next_cursor": next_cursor}

    @router.post("", response_model=response_model, status_code=status.HTTP_201_CREATED)
    async def create_item(body: ItemWrite, session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
        return wrap(await manager(service).create(session.vault_id, body.data, body.visibility))

    @router.get("/{item_id}", response_model=response_model)
    async def get_item(item_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
        return wrap(await manager(service).get(session.vault_id, item_id))

    @router.put("/{item_id}", response_model=response_model)
    async def update_item(
        item_id: uuid.UUID, body: ItemWrite, session: VaultSessionDep, service: LibraryServiceDep
    ) -> dict[str, Any]:
        return wrap(await manager(service).update(session.vault_id, item_id, body.data, body.visibility))

    @router.delete("/{item_id}", status_code=NO_CONTENT)
    async def delete_item(item_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep) -> Response:
        await manager(service).delete(session.vault_id, item_id)
        return Response(status_code=NO_CONTENT)

    @router.post("/{item_id}/duplicate", response_model=response_model, status_code=status.HTTP_201_CREATED)
    async def duplicate_item(
        item_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep
    ) -> dict[str, Any]:
        return wrap(await manager(service).duplicate(session.vault_id, item_id))

    @router.post("/{item_id}/judge", response_model=response_model)
    async def judge_item(
        item_id: uuid.UUID,
        session: VaultSessionDep,
        service: LibraryServiceDep,
        gateway_factory: GatewayFactoryDep,
        settings: SettingsDep,
        key_check: Annotated[KeyCheck, Depends(get_key_check)],
    ) -> dict[str, Any]:
        await key_check(session)
        return wrap(await manager(service).judge(session, item_id, gateway_factory, settings))

    @router.put(f"/{{item_id}}/{image_name}", response_model=response_model)
    async def put_image(
        item_id: uuid.UUID,
        request: Request,
        session: VaultSessionDep,
        service: LibraryServiceDep,
        settings: SettingsDep,
    ) -> dict[str, Any]:
        _, content = await read_upload(request, settings.max_image_bytes)
        return wrap(await manager(service).set_image(session.vault_id, item_id, content))

    @router.delete(f"/{{item_id}}/{image_name}", response_model=response_model)
    async def delete_image(item_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
        return wrap(await manager(service).clear_image(session.vault_id, item_id))

    @router.get("/{item_id}/export")
    async def export_item(
        item_id: uuid.UUID,
        session: VaultSessionDep,
        io: IoServiceDep,
        fmt: Annotated[ExportFormat, Query(alias="format")] = "vietrp",
        as_: Annotated[ExportAs, Query(alias="as")] = "json",
    ) -> Response:
        if kind == "character":
            return file_response(await io.export_character(session.vault_id, item_id, fmt=fmt, as_=as_))
        if fmt != "vietrp" or as_ != "json":
            raise AppError("validation_error", "Worlds export as vietrp json only", 422)
        return file_response(await io.export_world(session.vault_id, item_id))

    return router


characters_router = _build_content_router("/api/characters", "character", CharacterPage, CharacterResponse, "character")
worlds_router = _build_content_router("/api/worlds", "world", WorldPage, WorldResponse, "world")

personas_router = APIRouter(prefix="/api/personas", tags=["personas"])


@personas_router.get("", response_model=PersonaListResponse)
async def list_personas(session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
    return {"items": await service.personas.list_items(session.vault_id)}


@personas_router.post("", response_model=PersonaResponse, status_code=status.HTTP_201_CREATED)
async def create_persona(body: PersonaWrite, session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
    return {"persona": await service.personas.create(session.vault_id, body.data)}


@personas_router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(persona_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
    return {"persona": await service.personas.get(session.vault_id, persona_id)}


@personas_router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: uuid.UUID, body: PersonaWrite, session: VaultSessionDep, service: LibraryServiceDep
) -> dict[str, Any]:
    return {"persona": await service.personas.update(session.vault_id, persona_id, body.data)}


@personas_router.delete("/{persona_id}", status_code=NO_CONTENT)
async def delete_persona(persona_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep) -> Response:
    await service.personas.delete(session.vault_id, persona_id)
    return Response(status_code=NO_CONTENT)


@personas_router.put("/{persona_id}/avatar", response_model=PersonaResponse)
async def put_persona_avatar(
    persona_id: uuid.UUID,
    request: Request,
    session: VaultSessionDep,
    service: LibraryServiceDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    _, content = await read_upload(request, settings.max_image_bytes)
    return {"persona": await service.personas.set_image(session.vault_id, persona_id, content)}


@personas_router.delete("/{persona_id}/avatar", response_model=PersonaResponse)
async def delete_persona_avatar(
    persona_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep
) -> dict[str, Any]:
    return {"persona": await service.personas.set_image(session.vault_id, persona_id, None)}


lorebooks_router = APIRouter(prefix="/api/lorebooks", tags=["lorebooks"])


@lorebooks_router.get("", response_model=LorebookPage)
async def list_lorebooks(
    session: VaultSessionDep,
    service: LibraryServiceDep,
    q: str | None = None,
    limit: LimitQuery = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
) -> dict[str, Any]:
    items, next_cursor = await service.lorebooks.list_items(session.vault_id, q=q, limit=limit, cursor=cursor)
    return {"items": items, "next_cursor": next_cursor}


@lorebooks_router.post("", response_model=LorebookResponse, status_code=status.HTTP_201_CREATED)
async def create_lorebook(body: ItemWrite, session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
    return {"lorebook": await service.lorebooks.create(session.vault_id, body.data, body.visibility)}


@lorebooks_router.get("/{lorebook_id}", response_model=LorebookResponse)
async def get_lorebook(lorebook_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep) -> dict[str, Any]:
    return {"lorebook": await service.lorebooks.get(session.vault_id, lorebook_id)}


@lorebooks_router.put("/{lorebook_id}", response_model=LorebookResponse)
async def update_lorebook(
    lorebook_id: uuid.UUID, body: ItemWrite, session: VaultSessionDep, service: LibraryServiceDep
) -> dict[str, Any]:
    return {"lorebook": await service.lorebooks.update(session.vault_id, lorebook_id, body.data, body.visibility)}


@lorebooks_router.delete("/{lorebook_id}", status_code=NO_CONTENT)
async def delete_lorebook(lorebook_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep) -> Response:
    await service.lorebooks.delete(session.vault_id, lorebook_id)
    return Response(status_code=NO_CONTENT)


@lorebooks_router.post("/{lorebook_id}/duplicate", response_model=LorebookResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_lorebook(
    lorebook_id: uuid.UUID, session: VaultSessionDep, service: LibraryServiceDep
) -> dict[str, Any]:
    return {"lorebook": await service.lorebooks.duplicate(session.vault_id, lorebook_id)}


@lorebooks_router.get("/{lorebook_id}/export")
async def export_lorebook(
    lorebook_id: uuid.UUID,
    session: VaultSessionDep,
    io: IoServiceDep,
    fmt: Annotated[Literal["vietrp", "st"], Query(alias="format")] = "vietrp",
) -> Response:
    return file_response(await io.export_lorebook(session.vault_id, lorebook_id, fmt=fmt))


ROUTERS: list[APIRouter] = [characters_router, worlds_router, personas_router, lorebooks_router]
