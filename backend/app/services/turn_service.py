"""Runs single-chat turns in the background and bridges them to SSE.

The turn runs in its own task and pushes events into a queue; the HTTP response only drains the queue (and sends
`ping` while it is quiet). A client disconnect or `POST /stop` sets a cancel flag; the task then saves the partial
text as a `stopped` variant and finishes on its own, so nothing is lost when the connection drops.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Request

from app.agents.base import AgentContext
from app.core.config import Settings
from app.core.deps import GatewayFactory, GatewayFactoryDep, LLMServicesDep, SettingsDep, make_key_provider
from app.core.errors import AppError
from app.core.sessions import VaultSession
from app.llm.deps import LLMServices
from app.pipeline.single_turn import USER_SPEAKER, ChatContext, TurnConfig, TurnDeps, TurnInput, run_single_turn
from app.pipeline.world_turn import WorldChatContext, WorldTurnDeps, run_world_turn
from app.repositories.messages_repo import MemorySnapshotRecord, MessageRecord, NewVariant
from app.schemas.chat import ContinueRequest, RegenerateRequest, TurnRequest
from app.schemas.events import ErrorEvent, PingEvent, TurnEvent
from app.services.chat_service import (
    UnitOfWork,
    UnitOfWorkDep,
    chat_not_found,
    load_context,
    message_not_found,
    parse_chat_id,
    parse_message_id,
)

logger = logging.getLogger(__name__)

# Marks the end of a turn's event queue.
_END = object()

KeyCheck = Callable[[VaultSession], Awaitable[None]]


async def ensure_openrouter_key(vault_session: VaultSession) -> None:
    """Raises 400 `openrouter_key_missing` before any message is saved. Reads and discards the key."""
    await make_key_provider(vault_session)()


def get_key_check() -> KeyCheck:
    return ensure_openrouter_key


@dataclass(slots=True)
class RunningTurn:
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None


class TurnRegistry:
    """Which chats have a turn running. One per app instance; all access is on the event loop thread."""

    def __init__(self) -> None:
        self._running: dict[tuple[uuid.UUID, uuid.UUID], RunningTurn] = {}

    def register(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> RunningTurn:
        key = (vault_id, chat_id)
        if key in self._running:
            raise AppError("turn_running", "A turn is already running in this chat", 409)
        running = RunningTurn()
        self._running[key] = running
        return running

    def release(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> None:
        self._running.pop((vault_id, chat_id), None)

    def stop(self, vault_id: uuid.UUID, chat_id: uuid.UUID) -> bool:
        running = self._running.get((vault_id, chat_id))
        if running is None:
            return False
        running.cancel.set()
        return True


def get_turn_registry(request: Request) -> TurnRegistry:
    registry: TurnRegistry | None = getattr(request.app.state, "turn_registry", None)
    if registry is None:
        registry = TurnRegistry()
        request.app.state.turn_registry = registry
    return registry


TurnRegistryDep = Annotated[TurnRegistry, Depends(get_turn_registry)]


class UowTurnStore:
    """`TurnStore` over a unit of work: every call is one short transaction."""

    def __init__(self, uow: UnitOfWork, vault_id: uuid.UUID, chat_id: uuid.UUID) -> None:
        self._uow = uow
        self._vault_id = vault_id
        self._chat_id = chat_id

    async def next_seq(self) -> int:
        async with self._uow() as r:
            return await r.messages.next_seq(self._vault_id, self._chat_id)

    async def add_message(
        self,
        *,
        message_id: uuid.UUID,
        seq: int,
        speaker: str,
        meta: dict[str, Any],
        state_before: dict[str, Any],
        variant: NewVariant,
    ) -> None:
        async with self._uow() as r:
            await r.messages.add(
                self._vault_id,
                self._chat_id,
                message_id=message_id,
                seq=seq,
                speaker=speaker,
                meta=meta,
                state_before=state_before,
                variants=[variant],
            )
            await r.chats.update(self._vault_id, self._chat_id, {})
            await r.commit()

    async def add_variant(
        self,
        *,
        message_id: uuid.UUID,
        meta: dict[str, Any],
        variant: NewVariant,
    ) -> MessageRecord:
        async with self._uow() as r:
            updated = await r.messages.add_variant(
                self._vault_id,
                message_id,
                variant,
                meta=meta,
                activate=True,
            )
            await r.chats.update(self._vault_id, self._chat_id, {})
            await r.commit()
            return updated

    async def set_state(self, state: dict[str, Any]) -> None:
        async with self._uow() as r:
            await r.chats.update(self._vault_id, self._chat_id, {"state": state})
            await r.commit()

    async def add_snapshot(
        self,
        *,
        upto_seq: int,
        summary: str,
        events: Sequence[dict[str, Any]],
    ) -> MemorySnapshotRecord:
        async with self._uow() as r:
            snap = await r.messages.add_snapshot(
                self._vault_id,
                self._chat_id,
                upto_seq=upto_seq,
                summary=summary,
                events=events,
            )
            await r.commit()
            return snap


class TurnService:
    def __init__(
        self,
        uow: UnitOfWork,
        registry: TurnRegistry,
        gateway_factory: GatewayFactory,
        services: LLMServices,
        settings: Settings,
        cfg: TurnConfig | None = None,
    ) -> None:
        self._uow = uow
        self._registry = registry
        self._gateway_factory = gateway_factory
        self._services = services
        self._settings = settings
        self._cfg = cfg or TurnConfig()

    def _launch(
        self,
        vault_session: VaultSession,
        ctx: ChatContext | WorldChatContext,
        running: RunningTurn,
        inp: TurnInput,
    ) -> None:
        vault_id = vault_session.vault_id
        chat_id = ctx.chat_id
        gateway = self._gateway_factory(vault_session, chat_id)
        agent_ctx = AgentContext(vault_id=vault_id, chat_id=chat_id, llm=gateway, settings=self._settings)
        store = UowTurnStore(self._uow, vault_id, chat_id)
        deps: TurnDeps | WorldTurnDeps
        if isinstance(ctx, WorldChatContext):
            deps = WorldTurnDeps(
                ctx=ctx,
                store=store,
                agent_ctx=agent_ctx,
                corrections=self._services.corrections,
                cfg=self._cfg,
            )
        else:
            deps = TurnDeps(
                ctx=ctx,
                store=store,
                agent_ctx=agent_ctx,
                corrections=self._services.corrections,
                cfg=self._cfg,
            )
        running.task = asyncio.create_task(self._produce(deps, inp, running))

    async def start(self, vault_session: VaultSession, chat_id_text: str, body: TurnRequest) -> RunningTurn:
        """Validate, register (409 when a turn is already running) and launch the background turn."""
        vault_id = vault_session.vault_id
        chat_id = parse_chat_id(chat_id_text)
        async with self._uow() as r:
            ctx = await load_context(r, vault_id, chat_id, self._cfg)
        # No await between the registry check and the registration: only one concurrent request wins.
        running = self._registry.register(vault_id, chat_id)
        try:
            self._launch(vault_session, ctx, running, TurnInput(body.text, body.prefill))
        except BaseException:
            self._registry.release(vault_id, chat_id)
            raise
        return running

    async def start_continue(
        self, vault_session: VaultSession, chat_id_text: str, body: ContinueRequest | None = None
    ) -> RunningTurn:
        """Continue the story without saving a user message (`is_continue=True`)."""
        vault_id = vault_session.vault_id
        chat_id = parse_chat_id(chat_id_text)
        async with self._uow() as r:
            ctx = await load_context(r, vault_id, chat_id, self._cfg)
        running = self._registry.register(vault_id, chat_id)
        try:
            prefill = body.prefill if body is not None else None
            self._launch(vault_session, ctx, running, TurnInput(text="", prefill=prefill, is_continue=True))
        except BaseException:
            self._registry.release(vault_id, chat_id)
            raise
        return running

    async def start_regenerate(
        self,
        vault_session: VaultSession,
        message_id_text: str,
        body: RegenerateRequest | None = None,
        *,
        chat_id_text: str | None = None,
    ) -> RunningTurn:
        """Rewind any messages/snapshots after `target` and stream a new active variant for `target.speaker`."""
        vault_id = vault_session.vault_id
        message_id = parse_message_id(message_id_text)
        expected_chat_id = parse_chat_id(chat_id_text) if chat_id_text is not None else None

        async with self._uow() as r:
            if expected_chat_id is not None and await r.chats.get(vault_id, expected_chat_id) is None:
                raise chat_not_found()
            target = await r.messages.get_message(vault_id, message_id)
            if target is None or (expected_chat_id is not None and target.chat_id != expected_chat_id):
                raise message_not_found()
            if target.speaker == USER_SPEAKER:
                raise AppError("cannot_regenerate_user_message", "Cannot regenerate a user message", 422)
            chat_id = target.chat_id
            if await r.chats.get(vault_id, chat_id) is None:
                raise chat_not_found()

        running = self._registry.register(vault_id, chat_id)
        try:
            async with self._uow() as r:
                target = await r.messages.get_message(vault_id, message_id)
                if target is None or (expected_chat_id is not None and target.chat_id != expected_chat_id):
                    raise message_not_found()
                if target.speaker == USER_SPEAKER:
                    raise AppError("cannot_regenerate_user_message", "Cannot regenerate a user message", 422)
                await r.messages.delete_from_seq(vault_id, chat_id, target.seq + 1)
                await r.messages.delete_snapshots_after(vault_id, chat_id, target.seq)
                if target.state_before is not None:
                    await r.chats.update(vault_id, chat_id, {"state": copy.deepcopy(target.state_before)})
                else:
                    await r.chats.update(vault_id, chat_id, {})
                await r.commit()
                ctx = await load_context(r, vault_id, chat_id, self._cfg)
            prefill = body.prefill if body is not None else None
            self._launch(
                vault_session,
                ctx,
                running,
                TurnInput(text="", prefill=prefill, regenerate_message_id=target.id),
            )
        except BaseException:
            self._registry.release(vault_id, chat_id)
            raise
        return running

    async def _produce(self, deps: TurnDeps | WorldTurnDeps, inp: TurnInput, running: RunningTurn) -> None:
        try:
            stream = (
                run_world_turn(deps, inp, running.cancel)
                if isinstance(deps, WorldTurnDeps)
                else run_single_turn(deps, inp, running.cancel)
            )
            async for event in stream:
                running.queue.put_nowait(event)
        except Exception:
            logger.exception("turn task crashed")
            running.queue.put_nowait(ErrorEvent(code="internal_error"))
        finally:
            self._registry.release(deps.ctx.vault_id, deps.ctx.chat_id)
            running.queue.put_nowait(_END)

    async def events(self, running: RunningTurn) -> AsyncIterator[TurnEvent]:
        """Queue events plus a `ping` whenever nothing arrives for `sse_ping_interval_seconds`."""
        interval = float(self._settings.sse_ping_interval_seconds)
        finished = False
        try:
            while True:
                try:
                    item = await asyncio.wait_for(running.queue.get(), timeout=interval)
                except TimeoutError:
                    yield PingEvent()
                    continue
                if item is _END:
                    finished = True
                    return
                yield item
        finally:
            if not finished:
                # Client went away: stop cooperatively; the task saves the partial text by itself.
                running.cancel.set()

    async def sse_stream(self, running: RunningTurn) -> AsyncIterator[dict[str, str]]:
        """Format queued `TurnEvent`s as SSE dictionaries for `EventSourceResponse`."""
        async for event in self.events(running):
            yield {"event": event.type, "data": event.model_dump_json(exclude_none=True)}


def get_turn_service(
    uow: UnitOfWorkDep,
    registry: TurnRegistryDep,
    gateway_factory: GatewayFactoryDep,
    services: LLMServicesDep,
    settings: SettingsDep,
) -> TurnService:
    return TurnService(uow, registry, gateway_factory, services, settings)


TurnServiceDep = Annotated[TurnService, Depends(get_turn_service)]
