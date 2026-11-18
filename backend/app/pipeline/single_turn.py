"""Single-chat turn pipeline (architecture section 5.1): an async generator of typed `TurnEvent`s.

Order: commands, user message, bonds (first user message only), Orchestrator, assembly (safety rule always applied),
Writer, Director with retries, one-transaction persistence of the speaker's message, usage, done.
There is no State Keeper call in single chat (AGENTS.md section 4.5).

The generator never touches the database directly: it talks to a `TurnStore`, which the turn service backs with a
unit of work. Stopping is cooperative: the caller sets `cancel`, and the partial text is saved as a `stopped` variant.
"""

from __future__ import annotations

import copy
import difflib
import logging
import uuid
from collections.abc import AsyncIterator, Collection, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import ValidationError

from app.agents import archivist, bond_drafter, bond_selector, director, orchestrator, writer
from app.agents.base import AgentContext, Notice, run_non_critical
from app.agents.bond_drafter import BondRecord, DraftedBonds, bond_views
from app.core.config import (
    ANTI_REPEAT_THRESHOLD,
    ARCHIVIST_KEEP_RECENT,
    DIRECTOR_MAX_RETRIES,
    ORCHESTRATOR_RECENT_LINES,
    TURN_HISTORY_LIMIT,
)
from app.core.errors import AppError
from app.formats.card import VietrpCard
from app.formats.persona import Persona
from app.llm.client import LLMError
from app.llm.defaults import DEFAULT_MODELS
from app.llm.tokenizer import CorrectionTable
from app.llm.usage import Usage
from app.pipeline import lorebook, memory
from app.pipeline.commands import ParsedInput, parse_input
from app.pipeline.context_budget import BudgetSettings, needs_summary
from app.pipeline.lorebook import LoreBook, LoreSelection
from app.pipeline.prompt_assembler import (
    FALLBACK_USER_NAME,
    AssembledPrompt,
    AssemblyInput,
    HistoryMessage,
    assemble,
)
from app.pipeline.state_commands import STATE_COMMAND_KINDS, execute_state_command, npcs_from_state
from app.prompts.presets import PresetLayers
from app.repositories.messages_repo import MemorySnapshotRecord, MessageRecord, NewVariant, VariantRecord
from app.schemas.chat import ChatSettings
from app.schemas.events import (
    ArchivistEvent,
    BondsEvent,
    ContentEvent,
    DirectorEvent,
    DoneEvent,
    DraftEvent,
    ErrorEvent,
    NoticeEvent,
    ReasoningEvent,
    RejudgeEvent,
    ResetContentEvent,
    SpeakerEndEvent,
    SpeakerStartEvent,
    TurnEvent,
    UsageEvent,
)

logger = logging.getLogger(__name__)

USER_SPEAKER = "user"
NARRATOR_SPEAKER = "narrator"
NARRATOR_NAMES = frozenset({"narrator", "người dẫn truyện", "nguoi dan truyen"})
NARRATOR_LABEL = "Người dẫn truyện"
ANTI_REPEAT_HINT = (
    "Lần viết trước bị lặp nguyên văn tin trước; hãy viết diễn biến mới nối tiếp, không lặp lại câu chữ cũ."
)
CONTINUE_DIRECTOR_USER_MSG = "(người chơi không nói gì, muốn câu chuyện tự tiếp diễn)"
CONTINUE_SKIP_CRITERIA: tuple[str, ...] = ("answers_last", "no_new_events")


@dataclass(frozen=True, slots=True)
class TurnConfig:
    # Defaults and their rationale live in `core/config.py`.
    director_max_retries: int = DIRECTOR_MAX_RETRIES
    history_limit: int = TURN_HISTORY_LIMIT
    recent_lines: int = ORCHESTRATOR_RECENT_LINES


@dataclass(slots=True)
class ChatContext:
    """Everything a turn reads, loaded once before it starts."""

    vault_id: uuid.UUID
    chat_id: uuid.UUID
    character_id: str
    card: VietrpCard
    persona: Persona | None
    settings: ChatSettings
    state: dict[str, Any]
    books: list[LoreBook]
    history: list[MessageRecord]
    preset: PresetLayers = field(default_factory=PresetLayers)


class TurnStore(Protocol):
    """The writes a turn makes. Each call is its own transaction."""

    async def next_seq(self) -> int: ...

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
        """Message, variant, meta and `state_before` in one transaction."""
        ...

    async def add_variant(
        self,
        *,
        message_id: uuid.UUID,
        meta: dict[str, Any],
        variant: NewVariant,
    ) -> MessageRecord:
        """Append a regenerated variant to an existing message and activate it."""
        ...

    async def set_state(self, state: dict[str, Any]) -> None: ...

    async def add_snapshot(
        self,
        *,
        upto_seq: int,
        summary: str,
        events: Sequence[dict[str, Any]],
    ) -> MemorySnapshotRecord: ...


@dataclass(slots=True)
class TurnDeps:
    ctx: ChatContext
    store: TurnStore
    agent_ctx: AgentContext
    corrections: CorrectionTable
    cfg: TurnConfig = field(default_factory=TurnConfig)


@dataclass(frozen=True, slots=True)
class TurnInput:
    text: str
    prefill: str | None = None
    is_continue: bool = False
    regenerate_message_id: uuid.UUID | None = None


# --- helpers shared with the prompt preview ---


def history_messages(records: Sequence[MessageRecord]) -> list[HistoryMessage]:
    return [
        HistoryMessage("user" if r.speaker == USER_SPEAKER else "assistant", r.content) for r in records if r.content
    ]


def bond_records(state: dict[str, Any]) -> dict[str, BondRecord]:
    out: dict[str, BondRecord] = {}
    raw = state.get("bonds")
    for key, value in (raw if isinstance(raw, dict) else {}).items():
        try:
            out[str(key)] = BondRecord.model_validate(value)
        except ValidationError:
            continue
    return out


def writer_model(settings: ChatSettings) -> str:
    return settings.models.writer or DEFAULT_MODELS["writer"]


def build_assembly_input(
    ctx: ChatContext,
    messages: Sequence[HistoryMessage],
    *,
    corrections: CorrectionTable,
    card: VietrpCard | None = None,
    lore: lorebook.LoreSelection | None = None,
    card_fields: Sequence[str] | None = None,
    command: ParsedInput | None = None,
    prefill: str | None = None,
    narrator: bool = False,
) -> AssemblyInput:
    summary = ctx.state.get("summary")
    events = memory.format_state_events(ctx.state.get("events"))
    return AssemblyInput(
        card=card or ctx.card,
        messages=messages,
        model=writer_model(ctx.settings),
        persona=ctx.persona,
        bonds=bond_views(bond_records(ctx.state)),
        lore=lore.hits if lore is not None else (),
        summary=summary if isinstance(summary, str) else "",
        events=events,
        npcs=npcs_from_state(ctx.state.get("npcs", [])),
        card_fields=card_fields,
        preset=ctx.preset,
        nsfw=ctx.settings.nsfw,
        command=command,
        prefill=prefill,
        narrator=narrator,
        budget=BudgetSettings.from_memory(ctx.settings.memory.model_dump()),
        corrections=corrections,
    )


def select_lore(ctx: ChatContext, messages: Sequence[HistoryMessage]) -> LoreSelection:
    return lorebook.select(
        ctx.books, [m.content for m in messages], vault_id=ctx.vault_id, mode=ctx.settings.lorebook.mode
    )


# --- events ---


def notice_events(notices: Sequence[Notice]) -> list[TurnEvent]:
    events: list[TurnEvent] = []
    for notice in notices:
        # Generic failures of a non-critical agent get a per-agent code, e.g. `director_failed`.
        code = f"{notice.agent}_failed" if notice.code == "agent_failed" and notice.agent else notice.code
        events.append(NoticeEvent(code=code, agent=notice.agent or None, detail=notice.detail or None))
    return events


class _Usage:
    """Turns the gateway's collected usage into `usage` events and keeps a running total for `meta.usage`."""

    def __init__(self, deps: TurnDeps) -> None:
        self._deps = deps
        self.total = Usage()

    def drain(self, agent: str, model: str) -> list[TurnEvent]:
        return self.record(agent, model, self._deps.agent_ctx.llm.drain_usage())

    def record(self, agent: str, model: str, usages: Sequence[Usage]) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        for usage in usages:
            self.total = self.total + usage
            events.append(
                UsageEvent(
                    agent=agent,
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    reasoning_tokens=usage.reasoning_tokens,
                    cost=usage.cost or 0.0,
                )
            )
        return events

    def summary(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.total.prompt_tokens,
            "completion_tokens": self.total.completion_tokens,
            "cost": self.total.cost or 0.0,
        }


def _error_code(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.code
    if isinstance(exc, LLMError):
        return "llm_failed"
    return "internal_error"


# --- the turn ---


async def run_single_turn(deps: TurnDeps, inp: TurnInput, cancel: object) -> AsyncIterator[TurnEvent]:
    """Run one turn. `cancel` is an `asyncio.Event`-like object; setting it stops the turn cooperatively."""
    try:
        async for event in _turn(deps, inp, cancel):
            yield event
    except Exception as exc:
        if not isinstance(exc, AppError | LLMError):
            logger.exception("single turn failed")
        else:
            logger.warning("single turn failed (%s)", _error_code(exc))
        yield ErrorEvent(code=_error_code(exc))


def _is_set(cancel: Any) -> bool:
    return bool(cancel.is_set())


def _force_speaker(
    parsed: ParsedInput, plan: orchestrator.OrchestratorPlan, card: VietrpCard, character_id: str
) -> tuple[orchestrator.OrchestratorPlan, list[TurnEvent]]:
    """`/force @name`: the named speaker takes the turn, whatever the Orchestrator planned."""
    if parsed.kind != "force":
        return plan, []
    target = parsed.force_target.strip().casefold()
    if target in NARRATOR_NAMES:
        return plan.model_copy(update={"speaker_id": orchestrator.NARRATOR_ID, "speaker_kind": "narrator"}), []
    names = {card.name.casefold(), character_id.casefold(), *(a.casefold() for a in card.aliases)}
    if target in names:
        return plan.model_copy(update={"speaker_id": character_id, "speaker_kind": "character"}), []
    return plan, [NoticeEvent(code="force_target_unknown", detail="force target not found in this chat")]


async def _bonds_step(deps: TurnDeps, state: dict[str, Any], user_seq: int, usage: _Usage) -> AsyncIterator[TurnEvent]:
    """Bond Drafter then Selector (both non-critical). Writes `state.bonds` and emits `bonds`."""
    ctx, agent_ctx = deps.ctx, deps.agent_ctx
    settings = ctx.settings
    pair = bond_drafter.user_pair(ctx.card, ctx.character_id, ctx.persona, FALLBACK_USER_NAME)
    opening = next((m.content for m in ctx.history if m.speaker != USER_SPEAKER), "")
    drafter_model = settings.models.bond_drafter or DEFAULT_MODELS["bond_drafter"]
    drafted_result = await run_non_critical(
        bond_drafter.AGENT_ID,
        bond_drafter.run(
            agent_ctx,
            bond_drafter.AgentConfig(model=drafter_model),
            bond_drafter.DrafterInput([pair], opening=opening),
        ),
    )
    for event in notice_events(drafted_result.notices):
        yield event
    for event in usage.drain(bond_drafter.AGENT_ID, drafter_model):
        yield event
    drafted = drafted_result.value or DraftedBonds(options={pair.pair_id: []})
    selected: dict[str, bond_drafter.BondFields] = {}
    if any(drafted.options.values()):
        selector_model = settings.models.bond_selector or DEFAULT_MODELS["bond_selector"]
        picked = await run_non_critical(
            bond_selector.AGENT_ID,
            bond_selector.run(
                agent_ctx,
                bond_selector.AgentConfig(model=selector_model),
                bond_selector.SelectorInput([pair], drafted, opening=opening),
            ),
        )
        for event in notice_events(picked.notices):
            yield event
        for event in usage.drain(bond_selector.AGENT_ID, selector_model):
            yield event
        selected = picked.value or {}
    # Even with nothing drafted, the record is written with the card's pinned values so this step runs only once.
    records = bond_selector.apply_selection(bond_records(state), [pair], selected, user_seq)
    state["bonds"] = {key: record.model_dump(mode="json") for key, record in records.items()}
    await deps.store.set_state(state)
    yield BondsEvent(bonds=state["bonds"])


def _make_history_record(
    chat_id: uuid.UUID,
    message_id: uuid.UUID,
    seq: int,
    speaker: str,
    content: str,
    now: Any,
    *,
    meta: dict[str, Any] | None = None,
) -> MessageRecord:
    return MessageRecord(
        id=message_id,
        chat_id=chat_id,
        seq=seq,
        speaker=speaker,
        active_variant=0,
        meta=meta or {},
        state_before=None,
        created_at=now,
        variants=[VariantRecord(0, content, None, None, None, False, now)],
    )


@dataclass(slots=True)
class _SpeakResult:
    stopped: bool = False
    saved_record: MessageRecord | None = None


async def _turn(deps: TurnDeps, inp: TurnInput, cancel: Any) -> AsyncIterator[TurnEvent]:
    ctx, agent_ctx, store = deps.ctx, deps.agent_ctx, deps.store
    settings = ctx.settings
    parsed = (
        parse_input(inp.text)
        if not inp.is_continue and inp.regenerate_message_id is None
        else ParsedInput(kind="plain", message="")
    )
    if parsed.kind in STATE_COMMAND_KINDS:
        state_copy = copy.deepcopy(ctx.state)
        for event in await execute_state_command(parsed, state=state_copy, set_state=store.set_state, world=None):
            yield event
        return

    usage = _Usage(deps)
    state = copy.deepcopy(ctx.state)
    # Seed P4 memory keys cleanly on single chats (tolerating legacy rows without them).
    state.setdefault("bonds", {})
    state.setdefault("summary", "")
    state.setdefault("summary_upto", 0)
    state.setdefault("events", [])

    message_ids: list[str] = []
    regen_target: MessageRecord | None = None
    if inp.regenerate_message_id is not None:
        regen_target = next((m for m in ctx.history if m.id == inp.regenerate_message_id), None)
        if regen_target is None:
            raise AppError("message_not_found", "Message not found", 404)
        history_records = [m for m in ctx.history if m.seq < regen_target.seq]
        seq = regen_target.seq
    else:
        history_records = list(ctx.history)
        seq = await store.next_seq()

    has_prior_user_history = any(m.speaker == USER_SPEAKER for m in history_records)
    user_text = parsed.message
    user_name = ctx.persona.name if ctx.persona is not None else FALLBACK_USER_NAME
    user_seq = seq
    if not inp.is_continue and regen_target is None and user_text.strip():
        user_id = uuid.uuid4()
        await store.add_message(
            message_id=user_id,
            seq=seq,
            speaker=USER_SPEAKER,
            meta={},
            state_before=copy.deepcopy(state),
            variant=NewVariant(content=user_text),
        )
        message_ids.append(str(user_id))
        history_records.append(
            _make_history_record(ctx.chat_id, user_id, seq, USER_SPEAKER, user_text, agent_ctx.clock())
        )
        seq += 1

    should_draft_bonds = f"{ctx.character_id}:user" not in bond_records(state) and not (
        regen_target is not None and regen_target.seq == 0 and not has_prior_user_history
    )
    if should_draft_bonds:
        async for event in _bonds_step(deps, state, user_seq, usage):
            yield event
    if _is_set(cancel):
        yield DoneEvent(message_ids=message_ids)
        return

    ctx.state = state
    active_records = memory.unsummarized_records(history_records, state)
    history = history_messages(active_records)

    is_continue_turn = inp.is_continue or (
        regen_target is not None and (bool(regen_target.meta.get("is_continue")) or not has_prior_user_history)
    )
    if inp.is_continue:
        last_user = history[-1].content if (history and history[-1].role == "user") else ""
    elif regen_target is not None and is_continue_turn:
        last_user = ""
    else:
        last_user = next((m.content for m in reversed(history) if m.role == "user"), "")
    skip_criteria: tuple[str, ...] = CONTINUE_SKIP_CRITERIA if is_continue_turn else ()
    director_user_msg = (
        last_user if last_user.strip() else (CONTINUE_DIRECTOR_USER_MSG if is_continue_turn else last_user)
    )

    # Lorebook: keyword hits now, candidates for the Orchestrator (never the whole book).
    selection = select_lore(ctx, history)
    lines = [
        f"{user_name if m.role == 'user' else ctx.card.name}: {m.content}" for m in history[-deps.cfg.recent_lines :]
    ]
    orch_model = settings.models.orchestrator or DEFAULT_MODELS["orchestrator"]
    planned = await orchestrator.run(
        agent_ctx,
        orchestrator.AgentConfig(model=orch_model),
        orchestrator.OrchestratorInput(
            card=ctx.card,
            character_id=ctx.character_id,
            user_name=user_name,
            user_message=last_user,
            recent=lines,
            candidates=selection.candidates,
        ),
    )
    plan = planned.value
    for event in notice_events(planned.notices):
        yield event
    for event in usage.drain(orchestrator.AGENT_ID, orch_model):
        yield event
    if regen_target is not None:
        if regen_target.speaker == NARRATOR_SPEAKER:
            plan = plan.model_copy(update={"speaker_id": orchestrator.NARRATOR_ID, "speaker_kind": "narrator"})
        else:
            plan = plan.model_copy(update={"speaker_id": ctx.character_id, "speaker_kind": "character"})
    else:
        plan, force_notices = _force_speaker(parsed, plan, ctx.card, ctx.character_id)
        for event in force_notices:
            yield event
    yield plan.to_event()

    # The assembler sends every secret on the card it is given: keep only the ones the plan surfaced.
    shown_secrets = [s for s in ctx.card.secrets if s.id in plan.secret_ids] if "secrets" in plan.card_fields else []
    turn_card = ctx.card.model_copy(update={"secrets": shown_secrets})
    selection = lorebook.promote(selection, plan.lore_entry_ids)
    # The new user message is already part of `history`, so the assembler gets it as the newest window entry.
    prompt = assemble(
        build_assembly_input(
            ctx,
            history,
            corrections=deps.corrections,
            card=turn_card,
            lore=selection,
            card_fields=plan.card_fields,
            command=parsed if parsed.kind == "cmd" else None,
            prefill=inp.prefill,
            narrator=plan.speaker_kind == "narrator",
        )
    )

    speaker = (
        regen_target.speaker
        if regen_target is not None
        else (ctx.character_id if plan.speaker_kind == "character" else NARRATOR_SPEAKER)
    )
    prev_ai = next(
        (r.content for r in reversed(history_records) if r.speaker != USER_SPEAKER and r.content.strip()), ""
    )
    speak_result = _SpeakResult()
    async for event in _speak(
        deps,
        cancel,
        usage,
        prompt,
        speaker,
        seq,
        user_name,
        director_user_msg,
        state,
        message_ids,
        plan.turn_type,
        speak_result,
        prev_ai=prev_ai,
        skip_criteria=skip_criteria,
        regen_message_id=regen_target.id if regen_target is not None else None,
        is_continue_meta=is_continue_turn,
    ):
        yield event

    if speak_result.saved_record is not None:
        history_records.append(speak_result.saved_record)

    budget_settings = BudgetSettings.from_memory(settings.memory.model_dump())
    if (
        not _is_set(cancel)
        and not speak_result.stopped
        and (needs_summary(prompt.total_tokens, budget_settings) or prompt.history_dropped > 0)
    ):
        to_compress = memory.select_messages_to_compress(history_records, state, keep_recent=ARCHIVIST_KEEP_RECENT)
        if to_compress:
            arch_model = settings.models.archivist or DEFAULT_MODELS["archivist"]
            arch_out, arch_notices, arch_usages = await memory.compress_memory(
                agent_ctx,
                arch_model,
                state,
                to_compress,
                user_name=user_name,
                speaker_names={ctx.character_id: ctx.card.name},
                save_snapshot=lambda **kw: store.add_snapshot(**kw),
                set_state=store.set_state,
            )
            for event in notice_events(arch_notices):
                yield event
            for event in usage.record(archivist.AGENT_ID, arch_model, arch_usages):
                yield event
            if arch_out is not None:
                yield ArchivistEvent(summary=arch_out.summary, events_added=arch_out.events_added)
                if arch_out.events_added > 0:
                    pair = bond_drafter.user_pair(ctx.card, ctx.character_id, ctx.persona, FALLBACK_USER_NAME)
                    latest_seq = history_records[-1].seq if history_records else 0
                    updated_bonds, bond_notices, bond_usages = await memory.refresh_bonds_on_events(
                        agent_ctx,
                        settings,
                        [pair],
                        state,
                        seq=latest_seq,
                        set_state=store.set_state,
                    )
                    for event in notice_events(bond_notices):
                        yield event
                    for ag, mod, item in bond_usages:
                        for event in usage.record(ag, mod, [item]):
                            yield event
                    if updated_bonds is not None:
                        yield BondsEvent(bonds=updated_bonds)

    yield DoneEvent(message_ids=message_ids)


async def _speak(
    deps: TurnDeps,
    cancel: Any,
    usage: _Usage,
    prompt: AssembledPrompt,
    speaker: str,
    seq: int,
    user_name: str,
    user_message: str,
    state: dict[str, Any],
    message_ids: list[str],
    turn_type: str,
    out: _SpeakResult,
    *,
    prev_ai: str = "",
    skip_criteria: Collection[str] = (),
    regen_message_id: uuid.UUID | None = None,
    is_continue_meta: bool = False,
) -> AsyncIterator[TurnEvent]:
    """Writer + Director loop for one speaker, anti-repeat check, then persistence."""
    ctx, agent_ctx, cfg = deps.ctx, deps.agent_ctx, deps.cfg
    settings = ctx.settings
    message_id = regen_message_id or uuid.uuid4()
    yield SpeakerStartEvent(message_id=str(message_id), speaker=speaker, seq=seq)

    director_on = settings.director.enabled
    hold = director_on and settings.director.stream_mode == "hold_until_approved"
    writer_model_id = writer_model(settings)
    director_model = settings.models.director or DEFAULT_MODELS["director"]
    writer_cfg = writer.config_for(writer_model_id, settings.writer.reasoning)
    director_cfg = director.AgentConfig(model=director_model)
    character_name = ctx.card.name

    attempt = 0
    hints: list[str] = []
    rejected: str | None = None
    first_draft: str | None = None
    best_text = ""
    best: director.DirectorOutcome | None = None
    attempt_text = ""
    attempt_reasoning = ""
    best_reasoning = ""
    stopped = False

    while True:
        attempt_text = ""
        attempt_reasoning = ""
        writer_inp = writer.WriterInput(prompt, hints, rejected)
        writer_msgs = writer.build_messages(writer_inp)
        stream = writer.run(agent_ctx, writer_cfg, writer_inp)
        try:
            async for item in stream:
                if isinstance(item, writer.WriterReasoning):
                    if _is_set(cancel):
                        stopped = True
                        break
                    attempt_reasoning += item.text
                    yield ReasoningEvent(delta=item.text, attempt=attempt)
                    continue
                if not isinstance(item, writer.WriterDelta):
                    continue
                if _is_set(cancel):
                    stopped = True
                    break
                attempt_text += item.text
                if hold:
                    continue
                if director_on:
                    yield DraftEvent(delta=item.text)
                else:
                    yield ContentEvent(delta=item.text)
        finally:
            # Closing early (stop) cancels the upstream stream; usage seen so far is still recorded.
            await stream.aclose()  # type: ignore[attr-defined]
        for event in usage.drain(writer.AGENT_ID, writer_model_id):
            if isinstance(event, UsageEvent) and event.prompt_tokens > 0:
                memory.observe_writer_usage(deps.corrections, writer_model_id, writer_msgs, event.prompt_tokens)
            yield event
        if stopped or not director_on:
            break
        if first_draft is None:
            first_draft = attempt_text
        if attempt > 0:
            yield RejudgeEvent(attempt=attempt)
        judged = await run_non_critical(
            director.AGENT_ID,
            director.run(
                agent_ctx,
                director_cfg,
                director.DirectorInput(
                    character_name, user_name, user_message, attempt_text, attempt, skip_criteria=skip_criteria
                ),
            ),
        )
        for event in notice_events(judged.notices):
            yield event
        for event in usage.drain(director.AGENT_ID, director_model):
            yield event
        outcome = judged.value
        if outcome is None:
            # The Director failed: keep the draft as it is (non-critical agent).
            best_text = attempt_text if best is None else best_text
            best_reasoning = attempt_reasoning if best is None else best_reasoning
            break
        yield DirectorEvent(**outcome.verdict.model_dump())
        if best is None or director.better(best, outcome) is outcome:
            best, best_text, best_reasoning = outcome, attempt_text, attempt_reasoning
        if outcome.passed or attempt >= cfg.director_max_retries:
            break
        hints = director.fix_hints(outcome.verdict)
        rejected = attempt_text
        attempt += 1
        if not hold:
            yield ResetContentEvent(message_id=str(message_id))

    final_text = attempt_text if (stopped or not director_on) else (best_text or attempt_text)
    final_reasoning = (
        attempt_reasoning if (stopped or not director_on) else (best_reasoning if best_text else attempt_reasoning)
    )

    if (
        not stopped
        and prev_ai
        and final_text.strip()
        and difflib.SequenceMatcher(None, prev_ai[:1500], final_text.strip()[:1500]).ratio() > ANTI_REPEAT_THRESHOLD
    ):
        yield NoticeEvent(code="writer_repeated")
        yield ResetContentEvent(message_id=str(message_id))
        rewrite_text = ""
        rewrite_reasoning = ""
        rewrite_inp = writer.WriterInput(prompt, [ANTI_REPEAT_HINT])
        rewrite_msgs = writer.build_messages(rewrite_inp)
        stream = writer.run(agent_ctx, writer_cfg, rewrite_inp)
        try:
            async for item in stream:
                if isinstance(item, writer.WriterReasoning):
                    if _is_set(cancel):
                        stopped = True
                        break
                    rewrite_reasoning += item.text
                    yield ReasoningEvent(delta=item.text, attempt=attempt + 1)
                    continue
                if not isinstance(item, writer.WriterDelta):
                    continue
                if _is_set(cancel):
                    stopped = True
                    break
                rewrite_text += item.text
                if hold:
                    continue
                if director_on:
                    yield DraftEvent(delta=item.text)
                else:
                    yield ContentEvent(delta=item.text)
        finally:
            await stream.aclose()  # type: ignore[attr-defined]
        for event in usage.drain(writer.AGENT_ID, writer_model_id):
            if isinstance(event, UsageEvent) and event.prompt_tokens > 0:
                memory.observe_writer_usage(deps.corrections, writer_model_id, rewrite_msgs, event.prompt_tokens)
            yield event
        if rewrite_text.strip():
            final_text = rewrite_text
            final_reasoning = rewrite_reasoning
            attempt_text = rewrite_text
            if not stopped and director_on:
                attempt += 1
                yield RejudgeEvent(attempt=attempt)
                judged = await run_non_critical(
                    director.AGENT_ID,
                    director.run(
                        agent_ctx,
                        director_cfg,
                        director.DirectorInput(
                            character_name,
                            user_name,
                            user_message,
                            rewrite_text,
                            attempt,
                            skip_criteria=skip_criteria,
                        ),
                    ),
                )
                for event in notice_events(judged.notices):
                    yield event
                for event in usage.drain(director.AGENT_ID, director_model):
                    yield event
                if judged.value is not None:
                    best = judged.value
                    yield DirectorEvent(**best.verdict.model_dump())
        elif not stopped and not hold:
            yield ContentEvent(delta=final_text)
            attempt_text = final_text

    out.stopped = stopped
    # Show the final text when the client does not already hold it.
    if not stopped:
        if hold:
            yield ContentEvent(delta=final_text)
        elif director_on and final_text != attempt_text:
            yield ResetContentEvent(message_id=str(message_id))
            yield ContentEvent(delta=final_text)

    if not final_text.strip():
        # Nothing worth saving (stopped before the first token).
        return

    summary = usage.summary()
    meta: dict[str, Any] = {
        "usage": summary,
        "priority": best.priority if best is not None else 0,
        "attempts": attempt + 1,
        "turn_type": turn_type,
    }
    if final_reasoning.strip():
        meta["reasoning"] = final_reasoning
    if is_continue_meta:
        meta["is_continue"] = True
        meta["turn_id"] = str(uuid.uuid4())
    variant = NewVariant(
        content=final_text,
        draft=first_draft if first_draft is not None and first_draft != final_text else None,
        director=best.verdict.model_dump(mode="json") if best is not None and not stopped else None,
        usage=summary,
        stopped=stopped,
    )
    if regen_message_id is not None:
        saved = await deps.store.add_variant(message_id=message_id, meta=meta, variant=variant)
        variant_idx = saved.active_variant
        out.saved_record = saved
    else:
        await deps.store.add_message(
            message_id=message_id,
            seq=seq,
            speaker=speaker,
            meta=meta,
            state_before=copy.deepcopy(state),
            variant=variant,
        )
        variant_idx = 0
        out.saved_record = _make_history_record(
            ctx.chat_id,
            message_id,
            seq,
            speaker,
            final_text,
            agent_ctx.clock(),
            meta=meta,
        )
    message_ids.append(str(message_id))
    yield SpeakerEndEvent(message_id=str(message_id), variant_idx=variant_idx, stopped=stopped)
