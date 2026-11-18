"""Creator use cases: pools, session CRUD, conversational interview, 2-step generation, and library save."""

from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, cast

import anyio
from fastapi import Depends
from pydantic import ValidationError

from app.agents import card_judge, creator
from app.agents.base import AgentContext, run_non_critical
from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.core.deps import GatewayFactory, GatewayFactoryDep, SettingsDep
from app.core.errors import AppError
from app.core.sessions import VaultSession
from app.creator import load_character_pools, load_world_pools
from app.formats.common import FormatWarning
from app.formats.validate import validate_card, validate_world
from app.llm.client import LLMError
from app.llm.usage import Usage
from app.repositories.creator_repo import CreatorRepository, CreatorSessionRecord, SqlCreatorRepository
from app.schemas.creator import (
    CreatorDeltaEvent,
    CreatorDoneEvent,
    CreatorErrorEvent,
    CreatorEvent,
    CreatorFormattedEvent,
    CreatorGenerateIn,
    CreatorJudgedEvent,
    CreatorMessage,
    CreatorMessageEvent,
    CreatorMessageIn,
    CreatorMode,
    CreatorPoolsOut,
    CreatorRawEvent,
    CreatorSaveIn,
    CreatorSaveOut,
    CreatorSessionCreate,
    CreatorSessionOut,
    CreatorSessionUpdate,
    CreatorValidatedEvent,
)
from app.schemas.events import NoticeEvent, PingEvent, UsageEvent
from app.schemas.library import CharacterOut, TargetType, WorldOut
from app.services.library_service import LibraryService, Repos, get_repos, not_found

logger = logging.getLogger(__name__)

_END = object()


@dataclass(slots=True)
class CreatorRepos:
    creator: CreatorRepository
    library: Repos
    commit: Callable[[], Awaitable[None]]


CreatorUow = Callable[[], AbstractAsyncContextManager[CreatorRepos]]


def sql_creator_uow() -> CreatorUow:
    """Short-lived unit of work so SSE generators never hold a DB session across LLM calls."""

    @asynccontextmanager
    async def begin() -> Any:
        async with get_sessionmaker()() as db:
            yield CreatorRepos(
                creator=SqlCreatorRepository(db),
                library=get_repos(db),
                commit=db.commit,
            )

    return begin


def get_creator_uow() -> CreatorUow:
    return sql_creator_uow()


CreatorUowDep = Annotated[CreatorUow, Depends(get_creator_uow)]


def parse_session_id(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise not_found("Creator session") from exc


def _extract_target_type(seed: Mapping[str, Any]) -> TargetType:
    return "world" if seed.get("target_type") == "world" else "character"


def _merge_seed(existing_seed: Mapping[str, Any], incoming_seed: Mapping[str, Any]) -> dict[str, Any]:
    target_type = _extract_target_type(existing_seed)
    raw_target = incoming_seed.get("target_type")
    if raw_target in ("character", "world"):
        target_type = raw_target
    return {**incoming_seed, "target_type": target_type}


def _to_session_out(record: CreatorSessionRecord) -> CreatorSessionOut:
    mode: CreatorMode = "chat" if record.mode == "chat" else "slots"
    messages = [
        CreatorMessage(role=cast(Literal["user", "assistant"], msg["role"]), content=msg["content"])
        for msg in record.messages
        if isinstance(msg, Mapping) and msg.get("role") in ("user", "assistant") and isinstance(msg.get("content"), str)
    ]
    return CreatorSessionOut(
        id=str(record.id),
        mode=mode,
        target_type=_extract_target_type(record.seed),
        seed=copy.deepcopy(record.seed),
        messages=messages,
        raw=record.raw,
        result=copy.deepcopy(record.result) if record.result is not None else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@dataclass(slots=True)
class RunningCreatorStream:
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    queue: asyncio.Queue[Any] = field(default_factory=asyncio.Queue)
    task: asyncio.Task[None] | None = None


class CreatorService:
    """Orchestrates creator pools, sessions, chat interview, 2-step generation, and library saving."""

    def __init__(self, uow: CreatorUow, gateway_factory: GatewayFactory, settings: Settings) -> None:
        self._uow = uow
        self._gateway_factory = gateway_factory
        self._settings = settings

    async def get_pools(self) -> CreatorPoolsOut:
        character = await anyio.to_thread.run_sync(load_character_pools)
        world = await anyio.to_thread.run_sync(load_world_pools)
        return CreatorPoolsOut(character=character, world=world)

    async def create_session(self, vault_id: uuid.UUID, body: CreatorSessionCreate) -> CreatorSessionOut:
        seed = {**body.seed, "target_type": body.target_type}
        async with self._uow() as r:
            record = await r.creator.create(vault_id, mode=body.mode, seed=seed)
            await r.commit()
        return _to_session_out(record)

    async def get_session(self, vault_id: uuid.UUID, session_id_text: str) -> CreatorSessionOut:
        session_id = parse_session_id(session_id_text)
        async with self._uow() as r:
            record = await r.creator.get(vault_id, session_id)
        if record is None:
            raise not_found("Creator session")
        return _to_session_out(record)

    async def update_session(
        self, vault_id: uuid.UUID, session_id_text: str, body: CreatorSessionUpdate
    ) -> CreatorSessionOut:
        session_id = parse_session_id(session_id_text)
        async with self._uow() as r:
            existing = await r.creator.get(vault_id, session_id)
            if existing is None:
                raise not_found("Creator session")
            fields: dict[str, Any] = {}
            if body.seed is not None:
                fields["seed"] = _merge_seed(existing.seed, body.seed)
            if body.raw is not None:
                fields["raw"] = body.raw
            updated = await r.creator.update(vault_id, session_id, fields)
            if updated is None:
                raise not_found("Creator session")
            await r.commit()
        return _to_session_out(updated)

    async def start_message(
        self, vault_session: VaultSession, session_id_text: str, body: CreatorMessageIn
    ) -> RunningCreatorStream:
        session_id = parse_session_id(session_id_text)
        async with self._uow() as r:
            record = await r.creator.get(vault_session.vault_id, session_id)
        if record is None:
            raise not_found("Creator session")
        running = RunningCreatorStream()
        running.task = asyncio.create_task(self._produce_message(vault_session, record, body.text, running))
        return running

    async def start_generate(
        self, vault_session: VaultSession, session_id_text: str, body: CreatorGenerateIn
    ) -> RunningCreatorStream:
        session_id = parse_session_id(session_id_text)
        async with self._uow() as r:
            record = await r.creator.get(vault_session.vault_id, session_id)
            if record is None:
                raise not_found("Creator session")
            fields: dict[str, Any] = {}
            if body.seed is not None:
                fields["seed"] = _merge_seed(record.seed, body.seed)
            if body.raw is not None:
                fields["raw"] = body.raw
            if fields:
                updated = await r.creator.update(vault_session.vault_id, session_id, fields)
                if updated is None:
                    raise not_found("Creator session")
                await r.commit()
                record = updated
        running = RunningCreatorStream()
        running.task = asyncio.create_task(self._produce_generate(vault_session, record, body, running))
        return running

    async def _produce_message(
        self,
        vault_session: VaultSession,
        record: CreatorSessionRecord,
        user_text: str,
        running: RunningCreatorStream,
    ) -> None:
        vault_id = vault_session.vault_id
        gateway = self._gateway_factory(vault_session, None)
        agent_ctx = AgentContext(vault_id=vault_id, chat_id=None, llm=gateway, settings=self._settings)
        cfg = creator.AgentConfig()
        target_type = _extract_target_type(record.seed)
        try:
            done: creator.CreatorDone | None = None
            stream = creator.interview_stream(
                agent_ctx,
                cfg,
                target_type=target_type,
                seed=record.seed,
                messages=record.messages,
                user_message=user_text,
            )
            try:
                async for item in stream:
                    if running.cancel.is_set():
                        return
                    if isinstance(item, creator.CreatorDelta):
                        running.queue.put_nowait(CreatorDeltaEvent(delta=item.text))
                    else:
                        done = item
            finally:
                await stream.aclose()  # type: ignore[attr-defined]

            if done is None:
                return

            new_messages = [
                *copy.deepcopy(record.messages),
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": done.text},
            ]
            async with self._uow() as r:
                updated = await r.creator.update(vault_id, record.id, {"messages": new_messages})
                if updated is None:
                    raise not_found("Creator session")
                await r.commit()

            running.queue.put_nowait(CreatorMessageEvent(message=CreatorMessage(role="assistant", content=done.text)))
            for usage in gateway.drain_usage():
                running.queue.put_nowait(_usage_event(creator.AGENT_ID, cfg.model, usage))
            running.queue.put_nowait(CreatorDoneEvent(session=_to_session_out(updated)))
        except AppError as exc:
            running.queue.put_nowait(CreatorErrorEvent(code=exc.code))
        except LLMError as exc:
            running.queue.put_nowait(CreatorErrorEvent(code=exc.code))
        except Exception:
            logger.exception("creator message task crashed")
            running.queue.put_nowait(CreatorErrorEvent(code="internal_error"))
        finally:
            running.queue.put_nowait(_END)

    async def _produce_generate(
        self,
        vault_session: VaultSession,
        record: CreatorSessionRecord,
        body: CreatorGenerateIn,
        running: RunningCreatorStream,
    ) -> None:
        vault_id = vault_session.vault_id
        gateway = self._gateway_factory(vault_session, None)
        agent_ctx = AgentContext(vault_id=vault_id, chat_id=None, llm=gateway, settings=self._settings)
        creator_cfg = creator.AgentConfig()
        judge_cfg = card_judge.AgentConfig()
        target_type = _extract_target_type(record.seed)
        usages: list[tuple[str, str, Usage]] = []

        try:
            raw_text = record.raw or ""
            if not body.skip_raw or not raw_text.strip():
                draft_res = await creator.draft_raw(
                    agent_ctx,
                    creator_cfg,
                    target_type=target_type,
                    seed=record.seed,
                    messages=record.messages,
                )
                raw_text = draft_res.value
                usages.extend((creator.AGENT_ID, creator_cfg.model, u) for u in gateway.drain_usage())
                async with self._uow() as r:
                    updated_raw = await r.creator.update(vault_id, record.id, {"raw": raw_text})
                    if updated_raw is None:
                        raise not_found("Creator session")
                    await r.commit()
                    record = updated_raw
                running.queue.put_nowait(CreatorRawEvent(raw=raw_text))

            if running.cancel.is_set():
                return

            formatted_data, _, _ = await creator.format_json(
                agent_ctx,
                creator_cfg,
                target_type=target_type,
                raw_draft=raw_text,
                seed=record.seed,
            )
            usages.extend((creator.AGENT_ID, creator_cfg.model, u) for u in gateway.drain_usage())
            running.queue.put_nowait(CreatorFormattedEvent(data=formatted_data))

            validated_data, warnings = _validate_generated(target_type, formatted_data)
            running.queue.put_nowait(CreatorValidatedEvent(data=validated_data, warnings=warnings))

            if running.cancel.is_set():
                return

            judge_res = await run_non_critical(
                card_judge.AGENT_ID,
                card_judge.run(
                    agent_ctx,
                    judge_cfg,
                    card_judge.CardJudgeInput(target_type=target_type, data=validated_data),
                ),
            )
            usages.extend((card_judge.AGENT_ID, judge_cfg.model, u) for u in gateway.drain_usage())
            for notice in judge_res.notices:
                running.queue.put_nowait(NoticeEvent(code=notice.code, agent=notice.agent, detail=notice.detail))

            judge_score_dict: dict[str, Any] | None = None
            if judge_res.value is not None:
                judge_score_dict = judge_res.value.model_dump(mode="json")
                running.queue.put_nowait(CreatorJudgedEvent(judge_score=judge_res.value))

            result_payload: dict[str, Any] = {
                "data": validated_data,
                "warnings": [w.model_dump(mode="json") for w in warnings],
                "judge_score": judge_score_dict,
            }
            async with self._uow() as r:
                final_record = await r.creator.update(vault_id, record.id, {"result": result_payload})
                if final_record is None:
                    raise not_found("Creator session")
                await r.commit()

            for agent_name, model_name, usage in usages:
                running.queue.put_nowait(_usage_event(agent_name, model_name, usage))
            running.queue.put_nowait(CreatorDoneEvent(session=_to_session_out(final_record)))
        except AppError as exc:
            running.queue.put_nowait(CreatorErrorEvent(code=exc.code))
        except LLMError as exc:
            running.queue.put_nowait(CreatorErrorEvent(code=exc.code))
        except (ValidationError, ValueError):
            running.queue.put_nowait(CreatorErrorEvent(code="creator_format_failed"))
        except Exception:
            logger.exception("creator generate task crashed")
            running.queue.put_nowait(CreatorErrorEvent(code="internal_error"))
        finally:
            running.queue.put_nowait(_END)

    async def save_session(self, vault_id: uuid.UUID, session_id_text: str, body: CreatorSaveIn) -> CreatorSaveOut:
        session_id = parse_session_id(session_id_text)
        async with self._uow() as r:
            record = await r.creator.get(vault_id, session_id)
            if record is None:
                raise not_found("Creator session")
            target_type = _extract_target_type(record.seed)
            raw_data = body.data if body.data is not None else (record.result or {}).get("data")
            if not isinstance(raw_data, dict):
                raise AppError("creator_not_generated", "Creator session has no generated result to save", 422)

            library = LibraryService(r.library)
            manager = library.content(target_type)
            created = await manager.create(vault_id, raw_data, body.visibility, imported=False, commit=False)

            judge_score = (record.result or {}).get("judge_score")
            if isinstance(judge_score, dict):
                scored = await manager.repo.set_judge_score(vault_id, uuid.UUID(created.id), judge_score)
                if scored is not None:
                    created = manager.out(scored, vault_id, created.warnings)

            await r.commit()

        if isinstance(created, CharacterOut):
            return CreatorSaveOut(target_type=target_type, item_id=created.id, character=created)
        assert isinstance(created, WorldOut)
        return CreatorSaveOut(target_type=target_type, item_id=created.id, world=created)

    async def events(self, running: RunningCreatorStream) -> AsyncIterator[CreatorEvent]:
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
                running.cancel.set()

    async def sse_stream(self, running: RunningCreatorStream) -> AsyncIterator[dict[str, str]]:
        async for event in self.events(running):
            yield {"event": event.type, "data": event.model_dump_json(exclude_none=True)}


def _validate_generated(target_type: TargetType, data: dict[str, Any]) -> tuple[dict[str, Any], list[FormatWarning]]:
    if target_type == "character":
        card, warnings = validate_card(data, allow_missing_age=True)
        return card.model_dump(mode="json"), warnings
    world, warnings = validate_world(data)
    return world.model_dump(mode="json"), warnings


def _usage_event(agent: str, model: str, usage: Usage) -> UsageEvent:
    return UsageEvent(
        agent=agent,
        model=model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        reasoning_tokens=usage.reasoning_tokens,
        cost=usage.cost or 0.0,
    )


def get_creator_service(
    uow: CreatorUowDep,
    gateway_factory: GatewayFactoryDep,
    settings: SettingsDep,
) -> CreatorService:
    return CreatorService(uow, gateway_factory, settings)


CreatorServiceDep = Annotated[CreatorService, Depends(get_creator_service)]
