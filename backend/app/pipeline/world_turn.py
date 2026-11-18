"""World-chat turn pipeline (architecture section 5.2): an async generator of typed `TurnEvent`s.

Order: commands, user message, first-turn bonds for all pairs (non-critical), Orchestrator (`run_world`),
then either:
  - `per_character`: assemble per speaker, stream Writer through `SceneStreamFilter`, run Director with
    retries on stripped visible text, parse/merge `<scene>`, persist message + variant + `state_before`
    in one transaction, emit `scene` and `speaker_end`;
  - `single_call`: assemble once for `"group"`, stream Writer through `SceneStreamFilter`, run Director,
    parse/merge `<scene>`, split visible text into per-speaker messages, emit events and persist.
After the last speaker (when at least one ran and the turn was not cancelled), run State Keeper
(non-critical), persist state, emit `state`, and finish with `done`.
"""

from __future__ import annotations

import copy
import difflib
import logging
import re
import unicodedata
import uuid
from collections.abc import AsyncIterator, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.agents import archivist, bond_drafter, bond_selector, director, orchestrator, state_keeper, writer
from app.agents.base import AgentContext, run_non_critical
from app.agents.bond_drafter import BondRecord, DraftedBonds, bonds_for_speaker, world_pairs
from app.agents.orchestrator import WorldOrchestratorInput, WorldOrchestratorPlan, WorldPlannedSpeaker
from app.core.config import ANTI_REPEAT_THRESHOLD, ARCHIVIST_KEEP_RECENT
from app.core.errors import AppError
from app.formats.persona import Persona
from app.formats.world import Opening, VietrpWorld
from app.llm.client import LLMError
from app.llm.defaults import DEFAULT_MODELS
from app.llm.tokenizer import CorrectionTable
from app.llm.usage import Usage
from app.pipeline import lorebook, memory
from app.pipeline.commands import ParsedInput, parse_input
from app.pipeline.context_budget import BudgetSettings, needs_summary
from app.pipeline.lorebook import LoreBook, LoreSelection
from app.pipeline.prompt_assembler import FALLBACK_USER_NAME, AssembledPrompt, HistoryMessage
from app.pipeline.scene_parser import SceneStreamFilter, merge_scene, parse_scene_block, strip_scene_block
from app.pipeline.single_turn import (
    ANTI_REPEAT_HINT,
    CONTINUE_DIRECTOR_USER_MSG,
    CONTINUE_SKIP_CRITERIA,
    NARRATOR_LABEL,
    NARRATOR_NAMES,
    NARRATOR_SPEAKER,
    USER_SPEAKER,
    TurnConfig,
    TurnInput,
    TurnStore,
    bond_records,
    notice_events,
    writer_model,
)
from app.pipeline.state_commands import STATE_COMMAND_KINDS, execute_state_command, npcs_from_state
from app.pipeline.world_assembly import WorldAssemblyInput, WorldCastEntry, assemble_world
from app.prompts.presets import PresetLayers
from app.repositories.messages_repo import MessageRecord, NewVariant, VariantRecord
from app.schemas.chat import ChatSettings, GroupWriteMode
from app.schemas.events import (
    ArchivistEvent,
    BondsEvent,
    ContentEvent,
    DirectorEvent,
    DoneEvent,
    DraftEvent,
    ErrorEvent,
    NoticeEvent,
    RejudgeEvent,
    ResetContentEvent,
    SceneEvent,
    SpeakerEndEvent,
    SpeakerStartEvent,
    StateEvent,
    TurnEvent,
    UsageEvent,
)
from app.schemas.world_state import SceneDelta, SceneState, WorldState

logger = logging.getLogger(__name__)

GROUP_SPEAKER = "group"

_BRACKET_HEADER_RE = re.compile(r"^(?:\*\*)?\[([^\]\n]+)\](?:\*\*)?\s*:?\s*(.*)$")
_COLON_HEADER_RE = re.compile(r"^(?:\*\*)?([^:\n\"“”'\[\]]+?)(?:\s*\[([^\]\n]+)\])?(?:\*\*)?\s*:\s*(.*)$")
_NARRATOR_ALIASES = frozenset(
    {
        "narrator",
        "người dẫn truyện",
        "nguoi dan truyen",
        "dẫn truyện",
        "dan truyen",
        "người dẫn chuyện",
        "người dẫn truyện [narrator]",
    }
)


@dataclass(slots=True)
class WorldChatContext:
    """Everything a world turn or prompt preview reads, loaded once before starting."""

    vault_id: uuid.UUID
    chat_id: uuid.UUID
    world: VietrpWorld
    opening: Opening
    cast: list[WorldCastEntry]
    persona: Persona | None
    settings: ChatSettings
    state: dict[str, Any]
    books: list[LoreBook]
    history: list[MessageRecord]
    preset: PresetLayers = field(default_factory=PresetLayers)


@dataclass(slots=True)
class WorldTurnDeps:
    ctx: WorldChatContext
    store: TurnStore
    agent_ctx: AgentContext
    corrections: CorrectionTable
    cfg: TurnConfig = field(default_factory=TurnConfig)


# --- helpers shared with prompt preview ---


def _nfc_fold(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip()).casefold()


def slugify_name(text: str, fallback: str = "char") -> str:
    """NFD ASCII normalize + lowercase + underscore, bounded to `^[a-z0-9_]{1,40}$`."""
    lowered = text.strip().lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    ascii_only = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")[:40].strip("_")
    return slug or fallback


def speaker_label(speaker: str, cast_by_id: Mapping[str, WorldCastEntry], user_name: str) -> str:
    if speaker == USER_SPEAKER:
        return user_name
    if speaker == NARRATOR_SPEAKER:
        return NARRATOR_LABEL
    entry = cast_by_id.get(speaker)
    return entry.card.name if entry is not None else speaker


def world_history_messages(
    records: Sequence[MessageRecord],
    cast_by_id: Mapping[str, WorldCastEntry],
) -> list[HistoryMessage]:
    """Convert stored records to role-tagged messages, labelling each non-user speaker by name."""
    out: list[HistoryMessage] = []
    for record in records:
        if not record.content:
            continue
        if record.speaker == USER_SPEAKER:
            out.append(HistoryMessage("user", record.content))
            continue
        if record.speaker == NARRATOR_SPEAKER:
            label = NARRATOR_LABEL
        elif record.speaker in cast_by_id:
            label = cast_by_id[record.speaker].card.name
        else:
            label = record.speaker
        out.append(HistoryMessage("assistant", f"{label}: {record.content}"))
    return out


def format_recent_lines(
    records: Sequence[MessageRecord],
    cast_by_id: Mapping[str, WorldCastEntry],
    user_name: str,
) -> list[str]:
    return [
        f"{speaker_label(record.speaker, cast_by_id, user_name)}: {record.content}"
        for record in records
        if record.content
    ]


def select_world_lore(ctx: WorldChatContext, messages: Sequence[HistoryMessage]) -> LoreSelection:
    return lorebook.select(
        ctx.books, [m.content for m in messages], vault_id=ctx.vault_id, mode=ctx.settings.lorebook.mode
    )


def format_events(raw_events: Sequence[dict[str, Any]]) -> list[str]:
    return memory.format_state_events(raw_events)


def resolve_preview_speaker(ctx: WorldChatContext, world_state: WorldState, speaker: str | None) -> str:
    cast_slugs = [entry.id for entry in ctx.cast]
    cast_set = set(cast_slugs)
    if speaker is not None and (speaker in cast_set or speaker in (NARRATOR_SPEAKER, GROUP_SPEAKER)):
        return speaker
    if ctx.settings.group.write_mode == "single_call" and (world_state.present_ids or cast_slugs):
        return GROUP_SPEAKER
    first_present = next((cid for cid in world_state.present_ids if cid in cast_set), None)
    if first_present is not None:
        return first_present
    if cast_slugs:
        return cast_slugs[0]
    return NARRATOR_SPEAKER


def build_world_assembly_input(
    ctx: WorldChatContext,
    world_state: WorldState,
    messages: Sequence[HistoryMessage],
    *,
    speaker_id: str,
    corrections: CorrectionTable,
    cast: Sequence[WorldCastEntry] | None = None,
    lore: LoreSelection | None = None,
    card_fields: Sequence[str] | None = None,
    arriving_ids: Sequence[str] = (),
    safety_cast_ids: Sequence[str] = (),
    write_mode: GroupWriteMode = "per_character",
    entering: bool = False,
    command: ParsedInput | None = None,
    prefill: str | None = None,
) -> WorldAssemblyInput:
    mode: GroupWriteMode = "single_call" if write_mode == "single_call" else "per_character"
    active_present = list(dict.fromkeys([*world_state.present_ids, *arriving_ids]))
    bonds_speaker = GROUP_SPEAKER if mode == "single_call" else speaker_id
    return WorldAssemblyInput(
        world=ctx.world,
        cast=cast if cast is not None else ctx.cast,
        present_ids=world_state.present_ids,
        speaker_id=speaker_id,
        messages=messages,
        model=writer_model(ctx.settings),
        arriving_ids=arriving_ids,
        location_id=world_state.location_id,
        time=world_state.time,
        tension=world_state.tension,
        scene=world_state.scene,
        player_role=ctx.opening.player_role,
        persona=ctx.persona,
        bonds=bonds_for_speaker(bond_records(ctx.state), bonds_speaker, present_ids=active_present),
        lore=lore.hits if lore is not None else (),
        summary=world_state.summary,
        events=format_events(world_state.events),
        npcs=npcs_from_state(world_state.npcs),
        card_fields=card_fields,
        write_mode=mode,
        entering=entering,
        preset=ctx.preset,
        nsfw=ctx.settings.nsfw,
        command=command,
        prefill=prefill,
        budget=BudgetSettings.from_memory(ctx.settings.memory.model_dump()),
        corrections=corrections,
        safety_cast_ids=safety_cast_ids,
    )


# --- single_call speaker splitting ---


def _speaker_header_map(cast: Sequence[WorldCastEntry]) -> dict[str, str]:
    mapping: dict[str, str] = {key: NARRATOR_SPEAKER for key in _NARRATOR_ALIASES}
    for entry in cast:
        mapping[entry.id.casefold()] = entry.id
        mapping[_nfc_fold(entry.card.name)] = entry.id
        mapping[f"{_nfc_fold(entry.card.name)} [{entry.id.casefold()}]"] = entry.id
    for entry in cast:
        for alias in entry.card.aliases:
            if alias.strip():
                mapping.setdefault(_nfc_fold(alias), entry.id)
    last_words: dict[str, list[str]] = {}
    for entry in cast:
        parts = entry.card.name.split()
        if parts:
            last_words.setdefault(_nfc_fold(parts[-1]), []).append(entry.id)
    for word, ids in last_words.items():
        if len(ids) == 1:
            mapping.setdefault(word, ids[0])
    return mapping


def _match_speaker_header(line: str, header_map: Mapping[str, str]) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    bracket_match = _BRACKET_HEADER_RE.match(stripped)
    if bracket_match is not None:
        tag = _nfc_fold(bracket_match.group(1))
        if tag in header_map:
            return header_map[tag], bracket_match.group(2).strip()
    colon_match = _COLON_HEADER_RE.match(stripped)
    if colon_match is not None:
        label = _nfc_fold(colon_match.group(1))
        bracket_id = _nfc_fold(colon_match.group(2) or "")
        if bracket_id and bracket_id in header_map:
            return header_map[bracket_id], colon_match.group(3).strip()
        if label in header_map:
            return header_map[label], colon_match.group(3).strip()
    return None


def parse_single_call_segments(
    text: str,
    cast: Sequence[WorldCastEntry],
    planned_speakers: Sequence[WorldPlannedSpeaker],
) -> list[tuple[str, str]]:
    """Split `single_call` visible output into `[(speaker_id, segment_text), ...]`.

    Matches `[id]:`, `[id]`, `id:`, `Name:`, and `Người dẫn truyện:` at line starts; defaults to the first
    planned speaker when no speaker header is present. Consecutive segments for the same speaker are merged.
    """
    clean = text.strip()
    if not clean:
        return []
    default_speaker = planned_speakers[0].id if planned_speakers else NARRATOR_SPEAKER
    header_map = _speaker_header_map(cast)

    raw_segments: list[tuple[str, str]] = []
    current_speaker: str | None = None
    current_lines: list[str] = []

    def _flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            raw_segments.append((current_speaker or default_speaker, body))

    for line in clean.splitlines():
        matched = _match_speaker_header(line, header_map)
        if matched is not None:
            _flush()
            current_speaker, rest = matched
            current_lines = [rest] if rest else []
            continue
        if current_speaker is None and not line.strip() and not current_lines:
            continue
        current_lines.append(line)
    _flush()

    merged: list[tuple[str, str]] = []
    for sp, body in raw_segments:
        if merged and merged[-1][0] == sp:
            merged[-1] = (sp, f"{merged[-1][1]}\n{body}")
        else:
            merged.append((sp, body))
    return merged or [(default_speaker, clean)]


# --- usage, errors, commands ---


class _WorldUsage:
    """Turns gateway usage into `usage` events and tracks per-speaker usage for `meta.usage`."""

    def __init__(self, deps: WorldTurnDeps) -> None:
        self._deps = deps
        self.total = Usage()
        self.speaker = Usage()

    def reset_speaker(self) -> None:
        self.speaker = Usage()

    def drain(self, agent: str, model: str) -> list[TurnEvent]:
        return self.record(agent, model, self._deps.agent_ctx.llm.drain_usage())

    def record(self, agent: str, model: str, items: Sequence[Usage]) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        for item in items:
            self.total = self.total + item
            self.speaker = self.speaker + item
            events.append(
                UsageEvent(
                    agent=agent,
                    model=model,
                    prompt_tokens=item.prompt_tokens,
                    completion_tokens=item.completion_tokens,
                    reasoning_tokens=item.reasoning_tokens,
                    cost=item.cost or 0.0,
                )
            )
        return events

    def speaker_summary(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.speaker.prompt_tokens,
            "completion_tokens": self.speaker.completion_tokens,
            "cost": self.speaker.cost or 0.0,
        }


def _error_code(exc: Exception) -> str:
    if isinstance(exc, AppError):
        return exc.code
    if isinstance(exc, LLMError):
        return "llm_failed"
    return "internal_error"


def _is_set(cancel: Any) -> bool:
    return bool(cancel.is_set())


def _resolve_force_target(parsed: ParsedInput, cast: Sequence[WorldCastEntry]) -> tuple[str | None, bool]:
    """Return `(speaker_id_or_none, is_unknown)` for `/force @target`."""
    if parsed.kind != "force":
        return None, False
    raw = parsed.force_target.strip()
    folded = _nfc_fold(raw)
    if folded in NARRATOR_NAMES:
        return NARRATOR_SPEAKER, False
    for entry in cast:
        exact = {entry.id.casefold(), _nfc_fold(entry.card.name), *(_nfc_fold(a) for a in entry.card.aliases)}
        if folded in exact:
            return entry.id, False
    slugged = slugify_name(raw, "")
    for entry in cast:
        candidates = {
            entry.id,
            slugify_name(entry.card.name, ""),
            *(slugify_name(a, "") for a in entry.card.aliases if a.strip()),
        }
        parts = entry.card.name.split()
        last_word = _nfc_fold(parts[-1]) if parts else ""
        last_word_match = bool(last_word) and (folded == last_word or slugged == slugify_name(last_word, ""))
        if (slugged and slugged in candidates) or last_word_match:
            return entry.id, False
    return None, True


def _apply_world_force(
    parsed: ParsedInput,
    resolved_force: str | None,
    force_unknown: bool,
    plan: WorldOrchestratorPlan,
    world_state: WorldState,
    *,
    chain_max: int,
    default_sentences: int,
) -> tuple[WorldOrchestratorPlan, list[TurnEvent]]:
    if parsed.kind != "force":
        return plan, []
    if force_unknown or resolved_force is None:
        return plan, [NoticeEvent(code="force_target_unknown", detail="force target not found in this chat")]
    if plan.speakers and plan.speakers[0].id == resolved_force and plan.speakers[0].reason == "forced":
        return plan, []

    arriving = list(plan.arriving_ids)
    if (
        resolved_force != NARRATOR_SPEAKER
        and resolved_force not in world_state.present_ids
        and resolved_force not in arriving
    ):
        arriving.append(resolved_force)
    existing = next((sp for sp in plan.speakers if sp.id == resolved_force), None)
    entering = (
        resolved_force != NARRATOR_SPEAKER
        and resolved_force in arriving
        and resolved_force not in world_state.present_ids
    )
    forced_sp = WorldPlannedSpeaker(
        id=resolved_force,
        kind="narrator" if resolved_force == NARRATOR_SPEAKER else "character",
        sentences=existing.sentences if existing is not None else default_sentences,
        order=0,
        reason="forced",
        entering=entering,
        card_fields=list(existing.card_fields) if existing is not None else list(orchestrator.CORE_CARD_FIELDS),
        secret_ids=list(existing.secret_ids) if existing is not None else [],
    )
    others = [sp for sp in plan.speakers if sp.id != resolved_force][: max(0, chain_max - 1)]
    rest = [sp.model_copy(update={"order": idx}) for idx, sp in enumerate(others, start=1)]
    return plan.model_copy(update={"speakers": [forced_sp, *rest], "arriving_ids": arriving}), []


# --- bonds step ---


async def _world_bonds_step(
    deps: WorldTurnDeps,
    state: dict[str, Any],
    user_seq: int,
    usage: _WorldUsage,
) -> AsyncIterator[TurnEvent]:
    """Draft and select bonds for all cast pairs (non-critical). Preserves `seq=0` card pins."""
    ctx, agent_ctx = deps.ctx, deps.agent_ctx
    settings = ctx.settings
    pairs = world_pairs(ctx.cast, ctx.persona, FALLBACK_USER_NAME)
    if not pairs:
        return
    opening = next((m.content for m in ctx.history if m.speaker != USER_SPEAKER), "") or ctx.opening.message
    drafter_model = settings.models.bond_drafter or DEFAULT_MODELS["bond_drafter"]
    drafted_result = await run_non_critical(
        bond_drafter.AGENT_ID,
        bond_drafter.run(
            agent_ctx,
            bond_drafter.AgentConfig(model=drafter_model),
            bond_drafter.DrafterInput(pairs, opening=opening),
        ),
    )
    for event in notice_events(drafted_result.notices):
        yield event
    for event in usage.drain(bond_drafter.AGENT_ID, drafter_model):
        yield event

    drafted = drafted_result.value or DraftedBonds(options={p.pair_id: [] for p in pairs})
    selected: dict[str, bond_drafter.BondFields] = {}
    if any(drafted.options.values()):
        selector_model = settings.models.bond_selector or DEFAULT_MODELS["bond_selector"]
        picked = await run_non_critical(
            bond_selector.AGENT_ID,
            bond_selector.run(
                agent_ctx,
                bond_selector.AgentConfig(model=selector_model),
                bond_selector.SelectorInput(pairs, drafted, opening=opening),
            ),
        )
        for event in notice_events(picked.notices):
            yield event
        for event in usage.drain(bond_selector.AGENT_ID, selector_model):
            yield event
        selected = picked.value or {}

    records: dict[str, BondRecord] = bond_selector.apply_selection(bond_records(state), pairs, selected, user_seq)
    state["bonds"] = {key: record.model_dump(mode="json") for key, record in records.items()}
    await deps.store.set_state(state)
    yield BondsEvent(bonds=state["bonds"])


# --- shared Writer + Director + SceneStreamFilter loop ---


@dataclass(slots=True)
class _AttemptResult:
    final_visible: str = ""
    final_scene_raw: str | None = None
    first_draft: str | None = None
    best: director.DirectorOutcome | None = None
    attempts: int = 0
    stopped: bool = False
    last_streamed_visible: str = ""


async def _stream_writer_director(
    deps: WorldTurnDeps,
    cancel: Any,
    usage: _WorldUsage,
    prompt: AssembledPrompt,
    *,
    character_name: str,
    user_name: str,
    user_message: str,
    stream_message_id: uuid.UUID | None,
    stream_content_when_no_director: bool,
    out: _AttemptResult,
    prev_ai: str = "",
    skip_criteria: Collection[str] = (),
) -> AsyncIterator[TurnEvent]:
    """Run Writer (filtering `<scene>`) and Director retries, then anti-repeat check; populates `out` in place."""
    ctx, agent_ctx, cfg = deps.ctx, deps.agent_ctx, deps.cfg
    settings = ctx.settings
    director_on = settings.director.enabled
    hold = director_on and settings.director.stream_mode == "hold_until_approved"
    writer_model_id = writer_model(settings)
    director_model = settings.models.director or DEFAULT_MODELS["director"]
    writer_cfg = writer.AgentConfig(model=writer_model_id)
    director_cfg = director.AgentConfig(model=director_model)

    attempt = 0
    hints: list[str] = []
    rejected: str | None = None
    first_draft: str | None = None
    best_visible = ""
    best_scene_raw: str | None = None
    best: director.DirectorOutcome | None = None
    attempt_visible = ""
    attempt_scene_raw: str | None = None
    stopped = False

    while True:
        attempt_raw = ""
        stream_filter = SceneStreamFilter()
        writer_inp = writer.WriterInput(prompt, hints, rejected)
        writer_msgs = writer.build_messages(writer_inp)
        stream = writer.run(agent_ctx, writer_cfg, writer_inp)
        try:
            async for item in stream:
                if not isinstance(item, writer.WriterDelta):
                    continue
                if _is_set(cancel):
                    stopped = True
                    break
                attempt_raw += item.text
                visible_delta = stream_filter.feed(item.text)
                if not visible_delta or hold:
                    continue
                if director_on or not stream_content_when_no_director:
                    yield DraftEvent(delta=visible_delta)
                else:
                    yield ContentEvent(delta=visible_delta)
        finally:
            await stream.aclose()  # type: ignore[attr-defined]

        trailing_visible, _ = stream_filter.finish()
        if trailing_visible and not hold:
            if director_on or not stream_content_when_no_director:
                yield DraftEvent(delta=trailing_visible)
            else:
                yield ContentEvent(delta=trailing_visible)

        for event in usage.drain(writer.AGENT_ID, writer_model_id):
            if isinstance(event, UsageEvent) and event.prompt_tokens > 0:
                memory.observe_writer_usage(deps.corrections, writer_model_id, writer_msgs, event.prompt_tokens)
            yield event

        attempt_visible, attempt_scene_raw = strip_scene_block(attempt_raw)
        if stopped or not director_on:
            break
        if first_draft is None:
            first_draft = attempt_visible
        if attempt > 0:
            yield RejudgeEvent(attempt=attempt)

        judged = await run_non_critical(
            director.AGENT_ID,
            director.run(
                agent_ctx,
                director_cfg,
                director.DirectorInput(
                    character_name, user_name, user_message, attempt_visible, attempt, skip_criteria=skip_criteria
                ),
            ),
        )
        for event in notice_events(judged.notices):
            yield event
        for event in usage.drain(director.AGENT_ID, director_model):
            yield event

        outcome = judged.value
        if outcome is None:
            if best is None:
                best_visible, best_scene_raw = attempt_visible, attempt_scene_raw
            break
        yield DirectorEvent(**outcome.verdict.model_dump())
        if best is None or director.better(best, outcome) is outcome:
            best, best_visible, best_scene_raw = outcome, attempt_visible, attempt_scene_raw
        if outcome.passed or attempt >= cfg.director_max_retries:
            break
        hints = director.fix_hints(outcome.verdict)
        rejected = attempt_visible
        attempt += 1
        if not hold:
            yield ResetContentEvent(message_id=str(stream_message_id or GROUP_SPEAKER))

    final_visible = attempt_visible if (stopped or not director_on) else (best_visible or attempt_visible)
    final_scene_raw = (
        attempt_scene_raw if (stopped or not director_on) else (best_scene_raw if best_visible else attempt_scene_raw)
    )
    last_streamed_visible = attempt_visible

    if (
        not stopped
        and prev_ai
        and final_visible.strip()
        and difflib.SequenceMatcher(None, prev_ai[:1500], final_visible.strip()[:1500]).ratio() > ANTI_REPEAT_THRESHOLD
    ):
        yield NoticeEvent(code="writer_repeated")
        yield ResetContentEvent(message_id=str(stream_message_id or GROUP_SPEAKER))
        rewrite_raw = ""
        rewrite_filter = SceneStreamFilter()
        rewrite_inp = writer.WriterInput(prompt, [ANTI_REPEAT_HINT])
        rewrite_msgs = writer.build_messages(rewrite_inp)
        stream = writer.run(agent_ctx, writer_cfg, rewrite_inp)
        try:
            async for item in stream:
                if not isinstance(item, writer.WriterDelta):
                    continue
                if _is_set(cancel):
                    stopped = True
                    break
                rewrite_raw += item.text
                visible_delta = rewrite_filter.feed(item.text)
                if not visible_delta or hold:
                    continue
                if director_on or not stream_content_when_no_director:
                    yield DraftEvent(delta=visible_delta)
                else:
                    yield ContentEvent(delta=visible_delta)
        finally:
            await stream.aclose()  # type: ignore[attr-defined]

        trailing_visible, _ = rewrite_filter.finish()
        if trailing_visible and not hold:
            if director_on or not stream_content_when_no_director:
                yield DraftEvent(delta=trailing_visible)
            else:
                yield ContentEvent(delta=trailing_visible)

        for event in usage.drain(writer.AGENT_ID, writer_model_id):
            if isinstance(event, UsageEvent) and event.prompt_tokens > 0:
                memory.observe_writer_usage(deps.corrections, writer_model_id, rewrite_msgs, event.prompt_tokens)
            yield event

        rewrite_visible, rewrite_scene_raw = strip_scene_block(rewrite_raw)
        if rewrite_visible.strip():
            final_visible = rewrite_visible
            final_scene_raw = rewrite_scene_raw
            last_streamed_visible = rewrite_visible
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
                            rewrite_visible,
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
            if stream_content_when_no_director and not director_on:
                yield ContentEvent(delta=final_visible)
            elif director_on or not stream_content_when_no_director:
                yield DraftEvent(delta=final_visible)
            last_streamed_visible = final_visible

    out.final_visible = final_visible
    out.final_scene_raw = final_scene_raw
    out.first_draft = first_draft
    out.best = best
    out.attempts = attempt + 1
    out.stopped = stopped
    out.last_streamed_visible = last_streamed_visible


def _cast_for_speaker(
    cast: Sequence[WorldCastEntry],
    speaker_id: str,
    secret_ids: Sequence[str],
    card_fields: Sequence[str],
) -> list[WorldCastEntry]:
    """Strip un-surfaced secrets from every card before prompt assembly."""
    allowed = set(secret_ids) if "secrets" in card_fields else set()
    out: list[WorldCastEntry] = []
    for entry in cast:
        kept = [s for s in entry.card.secrets if s.id in allowed] if entry.id == speaker_id else []
        out.append(WorldCastEntry(id=entry.id, card=entry.card.model_copy(update={"secrets": kept})))
    return out


def _cast_for_single_call(
    cast: Sequence[WorldCastEntry], speakers: Sequence[WorldPlannedSpeaker]
) -> list[WorldCastEntry]:
    allowed_by_id = {
        sp.id: set(sp.secret_ids) for sp in speakers if sp.kind == "character" and "secrets" in sp.card_fields
    }
    out: list[WorldCastEntry] = []
    for entry in cast:
        allowed = allowed_by_id.get(entry.id, set())
        kept = [s for s in entry.card.secrets if s.id in allowed]
        out.append(WorldCastEntry(id=entry.id, card=entry.card.model_copy(update={"secrets": kept})))
    return out


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


async def _apply_scene_delta(
    deps: WorldTurnDeps,
    state: dict[str, Any],
    world_state: WorldState,
    scene_raw: str | None,
    *,
    speaker_id: str,
    write_mode: GroupWriteMode,
) -> tuple[SceneDelta | None, list[TurnEvent]]:
    delta, scene_notice = parse_scene_block(scene_raw)
    events: list[TurnEvent] = []
    if scene_notice is not None:
        events.extend(notice_events([scene_notice]))
    if delta is None:
        return None, events
    mode: GroupWriteMode = "single_call" if write_mode == "single_call" else "per_character"
    merged = merge_scene(world_state.scene, delta, speaker_id=speaker_id, write_mode=mode)
    world_state.scene = merged
    state["scene"] = merged.model_dump(mode="json")
    await deps.store.set_state(state)
    events.append(
        SceneEvent(
            delta=delta.model_dump(mode="json", exclude_unset=True),
            merged=state["scene"],
        )
    )
    return delta, events


# --- turn execution ---


async def run_world_turn(deps: WorldTurnDeps, inp: TurnInput, cancel: object) -> AsyncIterator[TurnEvent]:
    """Run one world turn. `cancel` is an `asyncio.Event`-like object; setting it stops the turn cooperatively."""
    try:
        async for event in _world_turn(deps, inp, cancel):
            yield event
    except Exception as exc:
        if not isinstance(exc, AppError | LLMError):
            logger.exception("world turn failed")
        else:
            logger.warning("world turn failed (%s)", _error_code(exc))
        yield ErrorEvent(code=_error_code(exc))


async def _world_turn(deps: WorldTurnDeps, inp: TurnInput, cancel: Any) -> AsyncIterator[TurnEvent]:
    ctx, agent_ctx, store = deps.ctx, deps.agent_ctx, deps.store
    settings = ctx.settings
    parsed = (
        parse_input(inp.text)
        if not inp.is_continue and inp.regenerate_message_id is None
        else ParsedInput(kind="plain", message="")
    )
    if parsed.kind in STATE_COMMAND_KINDS:
        state_copy = copy.deepcopy(ctx.state)
        for event in await execute_state_command(parsed, state=state_copy, set_state=store.set_state, world=ctx.world):
            yield event
        return

    usage = _WorldUsage(deps)
    state = copy.deepcopy(ctx.state)
    world_state = WorldState.model_validate(state)
    state = world_state.model_dump(mode="json")
    cast_by_id = {entry.id: entry for entry in ctx.cast}
    user_name = ctx.persona.name if ctx.persona is not None else FALLBACK_USER_NAME

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
    user_seq = seq
    user_text = parsed.message
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

    # Draft + select bonds on the first user turn (keeping any `seq=0` card pins intact).
    pairs = world_pairs(ctx.cast, ctx.persona, FALLBACK_USER_NAME)
    existing_bonds = bond_records(state)
    has_agent_drafted = any(
        c.seq > 0 or c.field not in record.pinned for record in existing_bonds.values() for c in record.changes
    )
    missing_pair = any(pair.pair_id not in existing_bonds for pair in pairs)
    should_draft_bonds = bool(pairs) and (missing_pair or (not has_prior_user_history and not has_agent_drafted))
    if regen_target is not None and regen_target.seq == 0 and not has_prior_user_history:
        should_draft_bonds = False
    if should_draft_bonds:
        async for event in _world_bonds_step(deps, state, user_seq, usage):
            yield event
        world_state.bonds = dict(state["bonds"])
    if _is_set(cancel):
        yield DoneEvent(message_ids=message_ids)
        return

    # Lorebook + Orchestrator plan (prompt only sees unsummarized history)
    active_records = memory.unsummarized_records(history_records, state)
    lore_messages = world_history_messages(active_records, cast_by_id)
    selection = select_world_lore(ctx, lore_messages)

    is_continue_turn = inp.is_continue or (
        regen_target is not None and (bool(regen_target.meta.get("is_continue")) or not has_prior_user_history)
    )
    if inp.is_continue:
        last_user = (
            active_records[-1].content if (active_records and active_records[-1].speaker == USER_SPEAKER) else ""
        )
    elif regen_target is not None and is_continue_turn:
        last_user = ""
    else:
        last_user = next((m.content for m in reversed(lore_messages) if m.role == "user"), "")
    skip_criteria: tuple[str, ...] = CONTINUE_SKIP_CRITERIA if is_continue_turn else ()
    director_user_msg = (
        last_user if last_user.strip() else (CONTINUE_DIRECTOR_USER_MSG if is_continue_turn else last_user)
    )

    recent_lines = format_recent_lines(active_records[-deps.cfg.recent_lines :], cast_by_id, user_name)
    all_user_msgs = [m.content for m in active_records if m.speaker == USER_SPEAKER and m.content]
    recent_user_msgs = all_user_msgs[:-1][-2:] if last_user else all_user_msgs[-2:]

    resolved_force, force_unknown = _resolve_force_target(parsed, ctx.cast)
    orch_model = settings.models.orchestrator or DEFAULT_MODELS["orchestrator"]
    orch_cfg = orchestrator.AgentConfig(model=orch_model)
    planned = await orchestrator.run_world(
        agent_ctx,
        orch_cfg,
        WorldOrchestratorInput(
            world=ctx.world,
            cast=ctx.cast,
            state=world_state,
            user_name=user_name,
            user_message=last_user,
            recent=recent_lines,
            recent_user_messages=recent_user_msgs,
            candidates=selection.candidates,
            chain_max=settings.group.chain_max,
            force_speaker=regen_target.speaker if regen_target is not None else resolved_force,
        ),
    )
    plan = planned.value
    for event in notice_events(planned.notices):
        yield event
    for event in usage.drain(orchestrator.AGENT_ID, orch_model):
        yield event

    if regen_target is not None:
        target_speaker = regen_target.speaker
        is_narrator = target_speaker == NARRATOR_SPEAKER
        existing = next((sp for sp in plan.speakers if sp.id == target_speaker), None)
        entering = not is_narrator and target_speaker not in world_state.present_ids
        arriving = list(plan.arriving_ids)
        if entering and target_speaker not in arriving:
            arriving.append(target_speaker)
        forced_sp = WorldPlannedSpeaker(
            id=target_speaker,
            kind="narrator" if is_narrator else "character",
            sentences=existing.sentences if existing is not None else orch_cfg.sentences,
            order=0,
            reason="regenerate",
            entering=entering,
            card_fields=list(existing.card_fields) if existing is not None else list(orchestrator.CORE_CARD_FIELDS),
            secret_ids=list(existing.secret_ids) if existing is not None else [],
        )
        plan = plan.model_copy(update={"speakers": [forced_sp], "arriving_ids": arriving})
    else:
        plan, force_notices = _apply_world_force(
            parsed,
            resolved_force,
            force_unknown,
            plan,
            world_state,
            chain_max=settings.group.chain_max,
            default_sentences=orch_cfg.sentences,
        )
        for event in force_notices:
            yield event
    yield plan.to_event()

    selection = lorebook.promote(selection, plan.lore_entry_ids)
    ctx.state = state  # Keep ctx.state aligned for `build_world_assembly_input`.

    spoken_ids: list[str] = []
    cancelled = False
    peak_prompt_tokens = 0
    max_history_dropped = 0
    director_on = settings.director.enabled
    hold = director_on and settings.director.stream_mode == "hold_until_approved"

    if regen_target is None and settings.group.write_mode == "single_call":
        has_present = bool(world_state.present_ids or plan.arriving_ids)
        assembly_speaker = GROUP_SPEAKER if has_present else NARRATOR_SPEAKER
        merged_fields = list(dict.fromkeys(f for sp in plan.speakers for f in sp.card_fields))
        turn_cast = _cast_for_single_call(ctx.cast, plan.speakers)
        prompt = assemble_world(
            build_world_assembly_input(
                ctx,
                world_state,
                lore_messages,
                speaker_id=assembly_speaker,
                corrections=deps.corrections,
                cast=turn_cast,
                lore=selection,
                card_fields=merged_fields or list(orchestrator.CORE_CARD_FIELDS),
                arriving_ids=plan.arriving_ids,
                safety_cast_ids=[sp.id for sp in plan.speakers],
                write_mode="single_call",
                entering=any(sp.entering for sp in plan.speakers),
                command=parsed if parsed.kind == "cmd" else None,
                prefill=inp.prefill,
            )
        )
        peak_prompt_tokens = prompt.total_tokens
        max_history_dropped = prompt.history_dropped
        char_label = ", ".join(speaker_label(sp.id, cast_by_id, user_name) for sp in plan.speakers) or ctx.world.name
        prev_ai = next(
            (m.content for m in reversed(history_records) if m.speaker != USER_SPEAKER and m.content.strip()), ""
        )
        usage.reset_speaker()
        res = _AttemptResult()
        async for event in _stream_writer_director(
            deps,
            cancel,
            usage,
            prompt,
            character_name=char_label,
            user_name=user_name,
            user_message=director_user_msg,
            stream_message_id=None,
            stream_content_when_no_director=False,
            out=res,
            prev_ai=prev_ai,
            skip_criteria=skip_criteria,
        ):
            yield event

        cancelled = res.stopped or _is_set(cancel)
        segments = parse_single_call_segments(res.final_visible, ctx.cast, plan.speakers)
        prev_state = copy.deepcopy(state)
        delta: SceneDelta | None = None
        scene_events: list[TurnEvent] = []
        if not res.stopped:
            delta, scene_events = await _apply_scene_delta(
                deps, state, world_state, res.final_scene_raw, speaker_id=NARRATOR_SPEAKER, write_mode="single_call"
            )
        usage_summary = usage.speaker_summary()
        turn_id = str(uuid.uuid4()) if is_continue_turn else None
        for idx, (seg_speaker, seg_text) in enumerate(segments):
            if not seg_text.strip():
                continue
            msg_id = uuid.uuid4()
            yield SpeakerStartEvent(message_id=str(msg_id), speaker=seg_speaker, seq=seq)
            yield ContentEvent(delta=seg_text)
            is_last = idx == len(segments) - 1
            seg_usage = usage_summary if idx == 0 else {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
            meta: dict[str, Any] = {
                "usage": seg_usage,
                "priority": res.best.priority if res.best is not None else 0,
                "attempts": res.attempts,
                "turn_type": plan.turn_type,
            }
            if is_continue_turn and turn_id is not None:
                meta["is_continue"] = True
                meta["turn_id"] = turn_id
            if is_last and delta is not None:
                meta["scene_delta"] = delta.model_dump(mode="json", exclude_unset=True)
            draft_text = (
                res.first_draft
                if idx == 0 and res.first_draft is not None and res.first_draft != res.final_visible
                else None
            )
            director_verdict = (
                res.best.verdict.model_dump(mode="json") if res.best is not None and not res.stopped else None
            )
            await store.add_message(
                message_id=msg_id,
                seq=seq,
                speaker=seg_speaker,
                meta=meta,
                state_before=copy.deepcopy(prev_state),
                variant=NewVariant(
                    content=seg_text,
                    draft=draft_text,
                    director=director_verdict,
                    usage=seg_usage,
                    stopped=res.stopped,
                ),
            )
            if is_last:
                for ev in scene_events:
                    yield ev
            message_ids.append(str(msg_id))
            spoken_ids.append(seg_speaker)
            history_records.append(
                _make_history_record(ctx.chat_id, msg_id, seq, seg_speaker, seg_text, agent_ctx.clock(), meta=meta)
            )
            seq += 1
            yield SpeakerEndEvent(message_id=str(msg_id), variant_idx=0, stopped=res.stopped)
        if not segments and scene_events:
            for ev in scene_events:
                yield ev
    else:
        turn_id = str(uuid.uuid4()) if is_continue_turn else None
        for idx, planned_sp in enumerate(plan.speakers):
            if _is_set(cancel):
                cancelled = True
                break
            turn_cast = _cast_for_speaker(ctx.cast, planned_sp.id, planned_sp.secret_ids, planned_sp.card_fields)
            current_messages = world_history_messages(memory.unsummarized_records(history_records, state), cast_by_id)
            prompt = assemble_world(
                build_world_assembly_input(
                    ctx,
                    world_state,
                    current_messages,
                    speaker_id=planned_sp.id,
                    corrections=deps.corrections,
                    cast=turn_cast,
                    lore=selection,
                    card_fields=None if planned_sp.kind == "narrator" else planned_sp.card_fields,
                    arriving_ids=plan.arriving_ids,
                    write_mode="per_character",
                    entering=planned_sp.entering,
                    command=parsed if parsed.kind == "cmd" else None,
                    prefill=inp.prefill if idx == 0 else None,
                )
            )
            peak_prompt_tokens = max(peak_prompt_tokens, prompt.total_tokens)
            max_history_dropped = max(max_history_dropped, prompt.history_dropped)
            msg_id = regen_target.id if regen_target is not None else uuid.uuid4()
            yield SpeakerStartEvent(message_id=str(msg_id), speaker=planned_sp.id, seq=seq)
            prev_ai = next(
                (m.content for m in reversed(history_records) if m.speaker != USER_SPEAKER and m.content.strip()), ""
            )
            usage.reset_speaker()
            res = _AttemptResult()
            async for event in _stream_writer_director(
                deps,
                cancel,
                usage,
                prompt,
                character_name=speaker_label(planned_sp.id, cast_by_id, user_name),
                user_name=user_name,
                user_message=director_user_msg,
                stream_message_id=msg_id,
                stream_content_when_no_director=True,
                out=res,
                prev_ai=prev_ai,
                skip_criteria=skip_criteria,
            ):
                yield event

            if not res.stopped:
                if hold:
                    if res.final_visible:
                        yield ContentEvent(delta=res.final_visible)
                elif director_on and res.final_visible != res.last_streamed_visible:
                    yield ResetContentEvent(message_id=str(msg_id))
                    if res.final_visible:
                        yield ContentEvent(delta=res.final_visible)

            if res.stopped or _is_set(cancel):
                cancelled = True

            prev_state = copy.deepcopy(state)
            delta, scene_events = None, []
            if not res.stopped:
                delta, scene_events = await _apply_scene_delta(
                    deps,
                    state,
                    world_state,
                    res.final_scene_raw,
                    speaker_id=planned_sp.id,
                    write_mode="per_character",
                )
            if not res.final_visible.strip():
                for ev in scene_events:
                    yield ev
                if cancelled:
                    break
                continue

            usage_summary = usage.speaker_summary()
            meta = {
                "usage": usage_summary,
                "priority": res.best.priority if res.best is not None else 0,
                "attempts": res.attempts,
                "turn_type": plan.turn_type,
            }
            if is_continue_turn and turn_id is not None:
                meta["is_continue"] = True
                meta["turn_id"] = turn_id
            if delta is not None:
                meta["scene_delta"] = delta.model_dump(mode="json", exclude_unset=True)
            draft_text = (
                res.first_draft if res.first_draft is not None and res.first_draft != res.final_visible else None
            )
            director_verdict = (
                res.best.verdict.model_dump(mode="json") if res.best is not None and not res.stopped else None
            )
            variant = NewVariant(
                content=res.final_visible,
                draft=draft_text,
                director=director_verdict,
                usage=usage_summary,
                stopped=res.stopped,
            )
            if regen_target is not None:
                saved = await store.add_variant(message_id=msg_id, meta=meta, variant=variant)
                variant_idx = saved.active_variant
                history_records.append(saved)
            else:
                await store.add_message(
                    message_id=msg_id,
                    seq=seq,
                    speaker=planned_sp.id,
                    meta=meta,
                    state_before=prev_state,
                    variant=variant,
                )
                variant_idx = 0
                history_records.append(
                    _make_history_record(
                        ctx.chat_id, msg_id, seq, planned_sp.id, res.final_visible, agent_ctx.clock(), meta=meta
                    )
                )
            for ev in scene_events:
                yield ev
            message_ids.append(str(msg_id))
            spoken_ids.append(planned_sp.id)
            seq += 1
            yield SpeakerEndEvent(message_id=str(msg_id), variant_idx=variant_idx, stopped=res.stopped)
            if cancelled:
                break

    if not cancelled and spoken_ids:
        sk_model = settings.models.state_keeper or DEFAULT_MODELS["state_keeper"]
        sk_cfg = state_keeper.AgentConfig(model=sk_model)
        sk_recent = format_recent_lines(history_records[-sk_cfg.recent_lines :], cast_by_id, user_name)
        sk_result = await run_non_critical(
            state_keeper.AGENT_ID,
            state_keeper.run(
                agent_ctx,
                sk_cfg,
                state_keeper.StateKeeperInput(
                    world=ctx.world,
                    cast=ctx.cast,
                    state=WorldState.model_validate(state),
                    user_name=user_name,
                    recent_lines=sk_recent,
                    speakers_this_turn=spoken_ids,
                    owed_ids=plan.owed_ids,
                    arriving_ids=plan.arriving_ids,
                ),
            ),
        )
        for event in notice_events(sk_result.notices):
            yield event
        for event in usage.drain(state_keeper.AGENT_ID, sk_cfg.model):
            yield event
        if sk_result.value is not None:
            outcome = sk_result.value
            preserved = outcome.state.model_copy(
                update={
                    "scene": SceneState.model_validate(state["scene"]),
                    "bonds": dict(state["bonds"]),
                    "summary": state["summary"],
                    "summary_upto": state["summary_upto"],
                    "events": list(state["events"]),
                    "manual": list(state["manual"]),
                }
            )
            state = preserved.model_dump(mode="json")
            await store.set_state(state)
            yield StateEvent(
                state=preserved,
                changed=outcome.changed,
                confidence=outcome.confidence,
            )

        budget_settings = BudgetSettings.from_memory(settings.memory.model_dump())
        if needs_summary(peak_prompt_tokens, budget_settings) or max_history_dropped > 0:
            to_compress = memory.select_messages_to_compress(history_records, state, keep_recent=ARCHIVIST_KEEP_RECENT)
            if to_compress:
                arch_model = settings.models.archivist or DEFAULT_MODELS["archivist"]
                speaker_names = {entry.id: entry.card.name for entry in ctx.cast}
                arch_out, arch_notices, arch_usages = await memory.compress_memory(
                    agent_ctx,
                    arch_model,
                    state,
                    to_compress,
                    user_name=user_name,
                    speaker_names=speaker_names,
                    save_snapshot=lambda **kw: store.add_snapshot(**kw),
                    set_state=store.set_state,
                )
                for event in notice_events(arch_notices):
                    yield event
                for event in usage.record(archivist.AGENT_ID, arch_model, arch_usages):
                    yield event
                if arch_out is not None:
                    yield ArchivistEvent(summary=arch_out.summary, events_added=arch_out.events_added)
                    if arch_out.events_added > 0 and pairs:
                        latest_seq = history_records[-1].seq if history_records else 0
                        updated_bonds, bond_notices, bond_usages = await memory.refresh_bonds_on_events(
                            agent_ctx,
                            settings,
                            pairs,
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

    for event in usage.drain("turn", ""):
        yield event
    yield DoneEvent(message_ids=message_ids)
