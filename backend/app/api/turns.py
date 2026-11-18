"""Turn routes: SSE turn, continue, regenerate, and stop endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from app.core.deps import VaultSessionDep
from app.schemas.chat import ContinueRequest, RegenerateRequest, TurnRequest
from app.services.chat_service import ChatServiceDep, chat_not_found, parse_chat_id
from app.services.turn_service import KeyCheck, TurnRegistryDep, TurnServiceDep, get_key_check

router = APIRouter(prefix="/api/chats", tags=["turns"])


@router.post("/{chat_id}/turn")
async def run_turn(
    chat_id: str,
    body: TurnRequest,
    session: VaultSessionDep,
    service: TurnServiceDep,
    key_check: Annotated[KeyCheck, Depends(get_key_check)],
) -> EventSourceResponse:
    await key_check(session)  # 400 openrouter_key_missing before anything is saved
    running = await service.start(session, chat_id, body)
    # `ping=0`: the turn stream sends its own typed `ping` events every sse_ping_interval_seconds.
    return EventSourceResponse(service.sse_stream(running), ping=0)


@router.post("/{chat_id}/continue")
async def continue_turn(
    chat_id: str,
    session: VaultSessionDep,
    service: TurnServiceDep,
    key_check: Annotated[KeyCheck, Depends(get_key_check)],
    body: ContinueRequest | None = None,
) -> EventSourceResponse:
    await key_check(session)
    running = await service.start_continue(session, chat_id, body)
    return EventSourceResponse(service.sse_stream(running), ping=0)


@router.post("/{chat_id}/messages/{message_id}/regenerate")
async def regenerate_chat_message(
    chat_id: str,
    message_id: str,
    session: VaultSessionDep,
    service: TurnServiceDep,
    key_check: Annotated[KeyCheck, Depends(get_key_check)],
    body: RegenerateRequest | None = None,
) -> EventSourceResponse:
    await key_check(session)
    running = await service.start_regenerate(session, message_id, body, chat_id_text=chat_id)
    return EventSourceResponse(service.sse_stream(running), ping=0)


@router.post("/{chat_id}/stop")
async def stop_turn(
    chat_id: str, session: VaultSessionDep, chats: ChatServiceDep, registry: TurnRegistryDep
) -> dict[str, bool]:
    parsed = parse_chat_id(chat_id)
    await chats.get(session.vault_id, parsed)  # 404 for another vault's chat
    return {"stopped": registry.stop(session.vault_id, parsed)}


__all__ = ["chat_not_found", "router"]
