"""Creator routes: pools, session CRUD, conversational interview SSE, 2-step generation SSE, and library save."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sse_starlette.sse import EventSourceResponse

from app.core.deps import VaultSessionDep
from app.schemas.creator import (
    CreatorGenerateIn,
    CreatorMessageIn,
    CreatorPoolsOut,
    CreatorSaveIn,
    CreatorSaveOut,
    CreatorSessionCreate,
    CreatorSessionOut,
    CreatorSessionUpdate,
)
from app.services.creator_service import CreatorServiceDep
from app.services.turn_service import KeyCheck, get_key_check

router = APIRouter(prefix="/api/creator", tags=["creator"])


@router.get("/pools", response_model=CreatorPoolsOut)
async def get_pools(_session: VaultSessionDep, service: CreatorServiceDep) -> CreatorPoolsOut:
    return await service.get_pools()


@router.post("/sessions", response_model=CreatorSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreatorSessionCreate,
    session: VaultSessionDep,
    service: CreatorServiceDep,
) -> CreatorSessionOut:
    return await service.create_session(session.vault_id, body)


@router.get("/sessions/{session_id}", response_model=CreatorSessionOut)
async def get_session(
    session_id: str,
    session: VaultSessionDep,
    service: CreatorServiceDep,
) -> CreatorSessionOut:
    return await service.get_session(session.vault_id, session_id)


@router.patch("/sessions/{session_id}", response_model=CreatorSessionOut)
async def update_session(
    session_id: str,
    body: CreatorSessionUpdate,
    session: VaultSessionDep,
    service: CreatorServiceDep,
) -> CreatorSessionOut:
    return await service.update_session(session.vault_id, session_id, body)


@router.post("/sessions/{session_id}/message")
async def post_message(
    session_id: str,
    body: CreatorMessageIn,
    session: VaultSessionDep,
    service: CreatorServiceDep,
    key_check: Annotated[KeyCheck, Depends(get_key_check)],
) -> EventSourceResponse:
    await key_check(session)
    running = await service.start_message(session, session_id, body)
    return EventSourceResponse(service.sse_stream(running), ping=0)


@router.post("/sessions/{session_id}/generate")
async def generate(
    session_id: str,
    session: VaultSessionDep,
    service: CreatorServiceDep,
    key_check: Annotated[KeyCheck, Depends(get_key_check)],
    body: CreatorGenerateIn | None = None,
) -> EventSourceResponse:
    await key_check(session)
    running = await service.start_generate(session, session_id, body or CreatorGenerateIn())
    return EventSourceResponse(service.sse_stream(running), ping=0)


@router.post(
    "/sessions/{session_id}/save",
    response_model=CreatorSaveOut,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
async def save_session(
    session_id: str,
    session: VaultSessionDep,
    service: CreatorServiceDep,
    body: CreatorSaveIn | None = None,
) -> CreatorSaveOut:
    return await service.save_session(session.vault_id, session_id, body or CreatorSaveIn())
