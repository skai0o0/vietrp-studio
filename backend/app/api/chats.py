"""Chat and message routes: CRUD, messages, bonds/state, summarize, undo, fork, edit, delete, swipe."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sse_starlette.sse import EventSourceResponse

from app.core.deps import VaultSessionDep
from app.schemas.chat import (
    ActiveVariantRequest,
    ChatCreate,
    ChatOut,
    ChatSummary,
    ChatUpdate,
    ForkRequest,
    MessageOut,
    MessageUpdate,
    PromptPreview,
    RegenerateRequest,
    UndoResult,
)
from app.schemas.world_state import StatePatch
from app.services.chat_service import (
    DEFAULT_CHATS_LIMIT,
    DEFAULT_MESSAGES_LIMIT,
    MAX_PAGE_LIMIT,
    ChatServiceDep,
    parse_chat_id,
    parse_message_id,
)
from app.services.turn_service import KeyCheck, TurnServiceDep, get_key_check

router = APIRouter(prefix="/api/chats", tags=["chats"])
messages_router = APIRouter(prefix="/api/messages", tags=["messages"])

LimitQuery = Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)]


@router.get("", response_model=list[ChatSummary])
async def list_chats(
    session: VaultSessionDep,
    service: ChatServiceDep,
    limit: LimitQuery = DEFAULT_CHATS_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ChatSummary]:
    return await service.list_chats(session.vault_id, limit=limit, offset=offset)


@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def create_chat(body: ChatCreate, session: VaultSessionDep, service: ChatServiceDep) -> ChatOut:
    return await service.create(session.vault_id, body)


@router.get("/{chat_id}", response_model=ChatOut)
async def get_chat(chat_id: str, session: VaultSessionDep, service: ChatServiceDep) -> ChatOut:
    return await service.get(session.vault_id, parse_chat_id(chat_id))


@router.patch("/{chat_id}", response_model=ChatOut)
async def update_chat(chat_id: str, body: ChatUpdate, session: VaultSessionDep, service: ChatServiceDep) -> ChatOut:
    return await service.update(session.vault_id, parse_chat_id(chat_id), body)


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(chat_id: str, session: VaultSessionDep, service: ChatServiceDep) -> Response:
    await service.remove(session.vault_id, parse_chat_id(chat_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
async def list_messages(
    chat_id: str,
    session: VaultSessionDep,
    service: ChatServiceDep,
    before: Annotated[int | None, Query(ge=0)] = None,
    limit: LimitQuery = DEFAULT_MESSAGES_LIMIT,
    include: Literal["drafts"] | None = None,
) -> list[MessageOut]:
    return await service.messages(
        session.vault_id, parse_chat_id(chat_id), before=before, limit=limit, include_drafts=include == "drafts"
    )


@router.get("/{chat_id}/prompt-preview", response_model=PromptPreview)
async def prompt_preview(
    chat_id: str,
    session: VaultSessionDep,
    service: ChatServiceDep,
    text: str = "",
    speaker: str | None = None,
) -> PromptPreview:
    return await service.prompt_preview(session.vault_id, parse_chat_id(chat_id), text, speaker=speaker)


@router.patch("/{chat_id}/state", response_model=ChatOut)
async def patch_state(chat_id: str, body: StatePatch, session: VaultSessionDep, service: ChatServiceDep) -> ChatOut:
    return await service.patch_state(session.vault_id, parse_chat_id(chat_id), body)


@router.post("/{chat_id}/summarize", response_model=ChatOut)
async def summarize_chat(
    chat_id: str,
    session: VaultSessionDep,
    service: ChatServiceDep,
    key_check: Annotated[KeyCheck, Depends(get_key_check)],
) -> ChatOut:
    return await service.summarize(session, parse_chat_id(chat_id), key_check=key_check)


@router.post("/{chat_id}/undo", response_model=UndoResult)
async def undo_chat(chat_id: str, session: VaultSessionDep, service: ChatServiceDep) -> UndoResult:
    return await service.undo(session.vault_id, parse_chat_id(chat_id))


@router.post("/{chat_id}/fork", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
async def fork_chat(
    chat_id: str,
    session: VaultSessionDep,
    service: ChatServiceDep,
    body: ForkRequest | None = None,
) -> ChatOut:
    return await service.fork(session.vault_id, parse_chat_id(chat_id), body)


@router.put("/{chat_id}/messages/{message_id}/active-variant", response_model=MessageOut)
async def set_chat_message_active_variant(
    chat_id: str,
    message_id: str,
    body: ActiveVariantRequest,
    session: VaultSessionDep,
    service: ChatServiceDep,
) -> MessageOut:
    return await service.set_active_variant(
        session.vault_id,
        parse_message_id(message_id),
        body.variant_idx,
        chat_id=parse_chat_id(chat_id),
    )


@router.patch("/{chat_id}/messages/{message_id}", response_model=MessageOut)
async def edit_chat_message(
    chat_id: str,
    message_id: str,
    body: MessageUpdate,
    session: VaultSessionDep,
    service: ChatServiceDep,
) -> MessageOut:
    return await service.edit_message(
        session.vault_id,
        parse_message_id(message_id),
        body.content,
        chat_id=parse_chat_id(chat_id),
    )


@router.delete("/{chat_id}/messages/{message_id}", response_model=UndoResult)
async def delete_chat_message(
    chat_id: str,
    message_id: str,
    session: VaultSessionDep,
    service: ChatServiceDep,
) -> UndoResult:
    return await service.delete_message(
        session.vault_id,
        parse_message_id(message_id),
        chat_id=parse_chat_id(chat_id),
    )


@messages_router.put("/{message_id}/active-variant", response_model=MessageOut)
async def set_message_active_variant(
    message_id: str,
    body: ActiveVariantRequest,
    session: VaultSessionDep,
    service: ChatServiceDep,
) -> MessageOut:
    return await service.set_active_variant(session.vault_id, parse_message_id(message_id), body.variant_idx)


@messages_router.patch("/{message_id}", response_model=MessageOut)
async def edit_message(
    message_id: str,
    body: MessageUpdate,
    session: VaultSessionDep,
    service: ChatServiceDep,
) -> MessageOut:
    return await service.edit_message(session.vault_id, parse_message_id(message_id), body.content)


@messages_router.delete("/{message_id}", response_model=UndoResult)
async def delete_message(
    message_id: str,
    session: VaultSessionDep,
    service: ChatServiceDep,
) -> UndoResult:
    return await service.delete_message(session.vault_id, parse_message_id(message_id))


@messages_router.post("/{message_id}/regenerate")
async def regenerate_message(
    message_id: str,
    session: VaultSessionDep,
    service: TurnServiceDep,
    key_check: Annotated[KeyCheck, Depends(get_key_check)],
    body: RegenerateRequest | None = None,
) -> EventSourceResponse:
    await key_check(session)
    running = await service.start_regenerate(session, message_id, body)
    return EventSourceResponse(service.sse_stream(running), ping=0)
