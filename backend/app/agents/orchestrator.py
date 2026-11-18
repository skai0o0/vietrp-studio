"""Orchestrator (architecture section 3, agent 1): plans one turn with atomic Decisions questions.

Single chat has one speaker (the character or the narrator). Candidates are pre-filtered before the call (lore
candidates come from `pipeline.lorebook`, card fields only if non-empty), so the question count stays small and never
grows with the whole lorebook (AGENTS.md section 4.4).

Role-name trap: this is the agent `vietrp-agent` calls "director".
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult, Notice
from app.core.config import (
    ADDRESS_CONFIDENCE,
    ARRIVE_THRESHOLD,
    CHAIN_THRESHOLD,
    LORE_AI_CANDIDATES,
    QUIET_THRESHOLD,
    QUIET_TURNS,
)
from app.formats.card import VietrpCard
from app.formats.world import Location, VietrpWorld
from app.llm.decisions import Choice, ChoiceAnswer, DecisionResult, Noul, NoulAnswer, Question
from app.llm.defaults import DEFAULT_MODELS
from app.pipeline.lorebook import LoreHit
from app.pipeline.world_assembly import WorldCastEntry, location_path
from app.prompts import render_prompt
from app.schemas.events import PlanEvent, PlanSpeaker
from app.schemas.world_state import WorldState

logger = logging.getLogger(__name__)

AGENT_ID = "orchestrator"
NARRATOR_ID = "narrator"
GROUP_ID = "group"
TURN_TYPES = ("dialogue", "action", "narration")
# World chat adds `scene_shift` (ported from `group.py: TURN_TYPES`).
WORLD_TURN_TYPES = ("dialogue", "action", "narration", "scene_shift")
# Speaker confidence below which an explicit name mention overrides the pick (group.py: direct()).
NAMING_CONFIDENCE_CUTOFF = 0.6
# Group addressee probability at or above which we assume the user spoke to the group, not a named individual.
GROUP_ADDRESSEE_CUTOFF = 0.5
# Secondary choice probability strong enough to chain as follow-up when `chain_max > 1` (primary holds the max share).
SECONDARY_SPEAKER_THRESHOLD = 0.3
# Minimum silent turns before surfacing a silence note to the world Orchestrator (group.py: direct()).
SILENCE_NOTE_TURNS = 2
# Card fields that are always loaded (architecture 4.1: "luon").
CORE_CARD_FIELDS = ("personality", "goals", "limits", "speech", "addressing", "relationships")
# Card fields the Orchestrator decides on, when the card has them at all (architecture 4.1: "Orchestrator chon").
OPTIONAL_CARD_FIELDS = ("appearance", "backstory", "extras")
FIELD_LABELS = {"appearance": "ngoại hình", "backstory": "quá khứ", "extras": "các mục tự do"}
_SEPARATOR = "---"


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["orchestrator"]
    # Sentences asked of the Writer when nothing else says otherwise (reference group.py uses 3-5 per speaker).
    sentences: int = Field(default=4, ge=1)
    # Probability at or above which a yes/no answer counts as yes.
    lore_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    field_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    # Most lore candidates asked about per turn (shared constant with the lorebook selector).
    max_lore_questions: int = Field(default=LORE_AI_CANDIDATES, ge=0)
    # How much recent chat the model sees.
    recent_messages: int = Field(default=4, ge=0)
    recent_chars: int = Field(default=600, ge=1)


@dataclass(frozen=True, slots=True)
class OrchestratorInput:
    card: VietrpCard
    character_id: str
    user_name: str
    user_message: str
    # Recent chat lines, oldest first, already formatted as "Name: text".
    recent: Sequence[str] = ()
    # `LoreSelection.candidates` from the lorebook step; never the whole book.
    candidates: Sequence[LoreHit] = ()


class OrchestratorPlan(BaseModel):
    turn_type: str
    speaker_id: str
    speaker_kind: Literal["character", "narrator"]
    sentences: int
    addressed_to: Literal["character", "nobody"]
    # Entry ids to pass to `lorebook.promote`.
    lore_entry_ids: list[str] = Field(default_factory=list)
    # Card field names for `AssemblyInput.card_fields` (core fields plus the chosen optional ones).
    card_fields: list[str] = Field(default_factory=list)
    # Secrets judged ready to surface. When non-empty `card_fields` contains "secrets"; the assembler sends every
    # secret on the card it is given, so the caller filters `card.secrets` to these ids first.
    secret_ids: list[str] = Field(default_factory=list)
    fallback: bool = False

    def to_event(self) -> PlanEvent:
        return PlanEvent(
            turn_type=self.turn_type,
            speakers=[PlanSpeaker(id=self.speaker_id, kind=self.speaker_kind, sentences=self.sentences)],
            lore_ids=self.lore_entry_ids,
            card_fields=self.card_fields,
        )


def split_choice(rendered: str) -> tuple[str, dict[str, str]]:
    """A choice template is `instructions`, a `---` line, then `key: description` lines."""
    head, _, tail = rendered.partition(_SEPARATOR)
    criteria: dict[str, str] = {}
    for line in tail.strip().splitlines():
        key, _, description = line.partition(":")
        if key.strip():
            criteria[key.strip()] = description.strip()
    return head.strip(), criteria


def _choice(template: str, **variables: str) -> Choice:
    instructions, criteria = split_choice(render_prompt(template, **variables))
    return Choice(criteria=criteria, instructions=instructions)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _optional_fields(card: VietrpCard) -> list[str]:
    return [name for name in OPTIONAL_CARD_FIELDS if getattr(card, name)]


def build_questions(cfg: AgentConfig, inp: OrchestratorInput, budget: int) -> dict[str, Question]:
    """Fixed questions first, then fields, secrets and lore candidates while the budget lasts."""
    card, user = inp.card, inp.user_name
    names = {"character": card.name, "user": user}
    questions: dict[str, Question] = {
        "turn_type": _choice("orchestrator/q_turn_type.j2", **names),
        "speaker": _choice("orchestrator/q_speaker.j2", **names),
        "addressee": _choice("orchestrator/q_addressee.j2", **names),
    }
    for name in _optional_fields(card):
        questions[f"field__{name}"] = Noul(
            instructions=render_prompt("orchestrator/q_field.j2", character=card.name, label=FIELD_LABELS[name])
        )
    for secret in card.secrets:
        questions[f"secret__{secret.id}"] = Noul(
            instructions=render_prompt("orchestrator/q_secret.j2", character=card.name, reveal_when=secret.reveal_when)
        )
    room = max(0, min(cfg.max_lore_questions, budget - len(questions)))
    for hit in inp.candidates[:room]:
        hint = _truncate(hit.entry.content.replace("\n", " "), 160)
        questions[f"lore__{hit.entry.id}"] = Noul(
            instructions=render_prompt(
                "orchestrator/q_lore.j2", title=hit.entry.title or hit.entry.id, hint=hint, user=user
            )
        )
    return questions


def build_state(cfg: AgentConfig, inp: OrchestratorInput) -> dict[str, str]:
    lines = (
        [_truncate(line, cfg.recent_chars) for line in inp.recent[-cfg.recent_messages :]]
        if cfg.recent_messages
        else []
    )
    state = {
        "character": render_prompt(
            "orchestrator/state.j2", character=inp.card.name, tagline=inp.card.tagline, user=inp.user_name
        ),
        "last_message": _truncate(inp.user_message, cfg.recent_chars * 2),
    }
    if lines:
        state["recent_chat"] = render_prompt("orchestrator/recent.j2", lines=lines)
    return state


def _picked(result: DecisionResult, key: str, allowed: Sequence[str], default: str) -> str:
    choice = result.choice(key).choice
    return choice if choice in allowed else default


def interpret(cfg: AgentConfig, inp: OrchestratorInput, result: DecisionResult) -> OrchestratorPlan:
    turn_type = _picked(result, "turn_type", TURN_TYPES, "dialogue")
    speaker = _picked(result, "speaker", ("character", "narrator"), "character")
    addressee = _picked(result, "addressee", ("character", "nobody"), "character")
    fields = list(CORE_CARD_FIELDS)
    for name in _optional_fields(inp.card):
        if result.noul(f"field__{name}") >= cfg.field_threshold:
            fields.append(name)
    secret_ids = [s.id for s in inp.card.secrets if result.noul(f"secret__{s.id}") >= cfg.field_threshold]
    if secret_ids:
        fields.append("secrets")
    lore_ids = [
        hit.entry.id
        for hit in inp.candidates
        if f"lore__{hit.entry.id}" in result.answers and result.noul(f"lore__{hit.entry.id}") >= cfg.lore_threshold
    ]
    narrator = speaker == "narrator"
    return OrchestratorPlan(
        turn_type=turn_type,
        speaker_id=NARRATOR_ID if narrator else inp.character_id,
        speaker_kind="narrator" if narrator else "character",
        sentences=cfg.sentences,
        addressed_to="character" if addressee == "character" else "nobody",
        lore_entry_ids=lore_ids,
        card_fields=fields,
        secret_ids=secret_ids,
    )


def fallback_plan(cfg: AgentConfig) -> OrchestratorPlan:
    """Used when the Decisions call fails: the narrator answers, with core card fields only (like the reference)."""
    return OrchestratorPlan(
        turn_type="dialogue",
        speaker_id=NARRATOR_ID,
        speaker_kind="narrator",
        sentences=cfg.sentences,
        addressed_to="nobody",
        card_fields=list(CORE_CARD_FIELDS),
        fallback=True,
    )


async def run(ctx: AgentContext, cfg: AgentConfig, inp: OrchestratorInput) -> AgentResult[OrchestratorPlan]:
    """Never raises (except cancellation): a failing call yields the fallback plan and a `notice`."""
    questions = build_questions(cfg, inp, ctx.settings.decisions_max_questions)
    try:
        result = await ctx.llm.decide(AGENT_ID, cfg.model, build_state(cfg, inp), questions)
        plan = interpret(cfg, inp, result)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("orchestrator failed (%s); using narrator fallback", type(exc).__name__)
        detail = getattr(exc, "code", type(exc).__name__)
        return AgentResult(
            value=fallback_plan(cfg),
            notices=[Notice(code="orchestrator_fallback", agent=AGENT_ID, detail=str(detail))],
        )
    return AgentResult(value=plan, usage=[result.usage])


# --- World chat (WP-U) ------------------------------------------------------------------------


def nearby_locations(locations: Sequence[Location], current_id: str) -> list[Location]:
    """Return ONLY current, parent, siblings (same `parent_id`), and direct children (architecture §4.2)."""
    by_id = {loc.id: loc for loc in locations}
    current = by_id.get(current_id)
    if current is None:
        return []
    out: list[Location] = [current]
    seen = {current.id}
    if current.parent_id is not None and current.parent_id in by_id:
        parent = by_id[current.parent_id]
        out.append(parent)
        seen.add(parent.id)
    for loc in locations:
        if loc.parent_id == current.parent_id and loc.id not in seen:
            out.append(loc)
            seen.add(loc.id)
    for loc in locations:
        if loc.parent_id == current.id and loc.id not in seen:
            out.append(loc)
            seen.add(loc.id)
    return out


def mentioned(card: VietrpCard, text: str) -> bool:
    """Case-insensitive word-boundary match against `card.aliases` or last word of `card.name` (group.py:mentioned)."""
    if not text:
        return False
    norm_text = unicodedata.normalize("NFC", text)
    parts = card.name.split()
    names = [*card.aliases, *(parts[-1:] if parts else [])]
    return any(
        re.search(r"(?<!\w)" + re.escape(unicodedata.normalize("NFC", n.strip())) + r"(?!\w)", norm_text, re.IGNORECASE)
        for n in names
        if n.strip()
    )


@dataclass(frozen=True, slots=True)
class WorldOrchestratorInput:
    world: VietrpWorld
    cast: Sequence[WorldCastEntry]
    state: WorldState
    user_name: str
    user_message: str
    recent: Sequence[str] = ()
    recent_user_messages: Sequence[str] = ()
    candidates: Sequence[LoreHit] = ()
    chain_max: int = 3
    force_speaker: str | None = None


class WorldPlannedSpeaker(BaseModel):
    id: str
    kind: Literal["character", "narrator"]
    sentences: int
    order: int
    reason: str = ""
    entering: bool = False
    card_fields: list[str] = Field(default_factory=list)
    secret_ids: list[str] = Field(default_factory=list)


class WorldOrchestratorPlan(BaseModel):
    turn_type: str
    speakers: list[WorldPlannedSpeaker]
    arriving_ids: list[str] = Field(default_factory=list)
    addressee: str | None = None
    owed_ids: list[str] = Field(default_factory=list)
    lore_entry_ids: list[str] = Field(default_factory=list)
    fallback: bool = False

    def to_event(self) -> PlanEvent:
        merged_fields = list(dict.fromkeys(field for sp in self.speakers for field in sp.card_fields))
        return PlanEvent(
            turn_type=self.turn_type,
            speakers=[
                PlanSpeaker(id=sp.id, kind=sp.kind, sentences=sp.sentences, order=sp.order, reason=sp.reason)
                for sp in self.speakers
            ],
            lore_ids=list(self.lore_entry_ids),
            card_fields=merged_fields,
        )


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _field_hint(card: VietrpCard, field_name: str) -> str:
    if field_name == "extras":
        joined = "; ".join(f"{k}: {v}" for k, v in card.extras.items())
        return _truncate(_one_line(joined), 160)
    raw = getattr(card, field_name, "")
    return _truncate(_one_line(str(raw)), 160)


def _partition_cast(
    inp: WorldOrchestratorInput,
) -> tuple[
    dict[str, WorldCastEntry],
    list[WorldCastEntry],
    list[WorldCastEntry],
    list[WorldCastEntry],
    list[WorldCastEntry],
]:
    """Return `(cast_by_id, present, mention_arriving, remaining_absent, all_absent)`."""
    cast_by_id = {entry.id: entry for entry in inp.cast}
    present = [cast_by_id[cid] for cid in dict.fromkeys(inp.state.present_ids) if cid in cast_by_id]
    present_set = {entry.id for entry in present}
    user_texts = [msg for msg in (*inp.recent_user_messages, inp.user_message) if msg]
    mention_arriving = [
        entry
        for entry in inp.cast
        if entry.id not in present_set and any(mentioned(entry.card, msg) for msg in user_texts)
    ]
    arriving_set = {entry.id for entry in mention_arriving}
    remaining_absent = [entry for entry in inp.cast if entry.id not in present_set and entry.id not in arriving_set]
    all_absent = [entry for entry in inp.cast if entry.id not in present_set]
    return cast_by_id, present, mention_arriving, remaining_absent, all_absent


def _noul(result: DecisionResult, key: str, default: float = 0.0) -> float:
    answer = result.answers.get(key)
    return answer.p if isinstance(answer, NoulAnswer) else default


def _choice_answer(result: DecisionResult, key: str) -> ChoiceAnswer | None:
    answer = result.answers.get(key)
    return answer if isinstance(answer, ChoiceAnswer) else None


def build_world_questions(cfg: AgentConfig, inp: WorldOrchestratorInput, budget: int) -> dict[str, Question]:
    """Build world-turn Decisions questions, strictly enforcing `len(questions) <= budget`."""
    if budget <= 0:
        return {}
    _, present, mention_arriving, remaining_absent, all_absent = _partition_cast(inp)
    candidate_entries = [*present, *mention_arriving]
    user = inp.user_name

    def _entry_var(entry: WorldCastEntry) -> dict[str, str]:
        return {"id": entry.id, "name": _one_line(entry.card.name), "tagline": _one_line(entry.card.tagline)}

    questions: dict[str, Question] = {}

    def _add(key: str, question: Question) -> None:
        if len(questions) < budget:
            questions[key] = question

    _add("turn_type", _choice("orchestrator/q_world_turn_type.j2", user=user))

    sp_instr, sp_criteria = split_choice(
        render_prompt(
            "orchestrator/q_world_speaker.j2",
            user=user,
            present=[_entry_var(e) for e in present],
            arriving=[_entry_var(e) for e in mention_arriving],
        )
    )
    _add("speaker", Choice(criteria=sp_criteria, instructions=sp_instr))

    addr_instr, addr_criteria = split_choice(
        render_prompt(
            "orchestrator/q_world_addressee.j2",
            user=user,
            present=[_entry_var(e) for e in present],
            absent=[_entry_var(e) for e in all_absent],
        )
    )
    _add("addressee", Choice(criteria=addr_criteria, instructions=addr_instr))

    for entry in remaining_absent:
        if len(questions) >= budget:
            break
        _add(
            f"arrive__{entry.id}",
            Noul(
                instructions=render_prompt(
                    "orchestrator/q_world_arrive.j2",
                    character=entry.card.name,
                    tagline=_one_line(entry.card.tagline),
                )
            ),
        )

    if inp.chain_max > 1:
        for entry in candidate_entries:
            if len(questions) >= budget:
                break
            _add(
                f"followup__{entry.id}",
                Noul(
                    instructions=render_prompt(
                        "orchestrator/q_world_followup.j2",
                        character=entry.card.name,
                        tagline=_one_line(entry.card.tagline),
                        user=user,
                    )
                ),
            )

    for entry in candidate_entries:
        for field_name in _optional_fields(entry.card):
            if len(questions) >= budget:
                break
            _add(
                f"field__{entry.id}__{field_name}",
                Noul(
                    instructions=render_prompt(
                        "orchestrator/q_world_field.j2",
                        character=entry.card.name,
                        label=FIELD_LABELS[field_name],
                        hint=_field_hint(entry.card, field_name),
                    )
                ),
            )

    for entry in candidate_entries:
        for secret in entry.card.secrets:
            if len(questions) >= budget:
                break
            _add(
                f"secret__{entry.id}__{secret.id}",
                Noul(
                    instructions=render_prompt(
                        "orchestrator/q_secret.j2",
                        character=entry.card.name,
                        reveal_when=secret.reveal_when,
                    )
                ),
            )

    room = max(0, min(cfg.max_lore_questions, budget - len(questions)))
    for hit in inp.candidates[:room]:
        hint = _truncate(_one_line(hit.entry.content), 160)
        _add(
            f"lore__{hit.entry.id}",
            Noul(
                instructions=render_prompt(
                    "orchestrator/q_lore.j2",
                    title=hit.entry.title or hit.entry.id,
                    hint=hint,
                    user=user,
                )
            ),
        )
    return questions


def build_world_state(cfg: AgentConfig, inp: WorldOrchestratorInput) -> dict[str, str]:
    """Build world context, recent chat, silence notes (>= 2 turns), and last message."""
    cast_by_id = {entry.id: entry for entry in inp.cast}
    present_names = [cast_by_id[cid].card.name for cid in dict.fromkeys(inp.state.present_ids) if cid in cast_by_id]
    nearby = [loc.name for loc in nearby_locations(inp.world.locations, inp.state.location_id)]
    loc_path = location_path(inp.world.locations, inp.state.location_id)
    tension = max(0, min(4, inp.state.tension))
    quiet = [
        {"name": cast_by_id[cid].card.name, "turns": turns}
        for cid in dict.fromkeys(inp.state.present_ids)
        if cid in cast_by_id and (turns := inp.state.silence.get(cid, 0)) >= SILENCE_NOTE_TURNS
    ]
    last_msg = f"{inp.user_name}: {inp.user_message}" if inp.user_message.strip() else ""
    state: dict[str, str] = {
        "world_context": render_prompt(
            "orchestrator/world_state.j2",
            world_name=inp.world.name,
            location_path=loc_path,
            nearby=nearby,
            time=inp.state.time.strip(),
            tension=tension,
            user=inp.user_name,
            present=present_names,
        ),
        "silence_notes": render_prompt("orchestrator/world_silence.j2", quiet=quiet),
        "last_message": _truncate(last_msg, cfg.recent_chars * 2),
    }
    lines = (
        [_truncate(line, cfg.recent_chars) for line in inp.recent[-cfg.recent_messages :]]
        if cfg.recent_messages
        else []
    )
    if lines:
        state["recent_chat"] = render_prompt("orchestrator/recent.j2", lines=lines)
    return state


def _speaker_fields_and_secrets(
    cfg: AgentConfig, cast_by_id: dict[str, WorldCastEntry], result: DecisionResult, speaker_id: str
) -> tuple[list[str], list[str]]:
    if speaker_id not in cast_by_id:
        return list(CORE_CARD_FIELDS), []
    card = cast_by_id[speaker_id].card
    fields = list(CORE_CARD_FIELDS)
    for name in _optional_fields(card):
        if _noul(result, f"field__{speaker_id}__{name}") >= cfg.field_threshold:
            fields.append(name)
    secret_ids = [
        secret.id
        for secret in card.secrets
        if _noul(result, f"secret__{speaker_id}__{secret.id}") >= cfg.field_threshold
    ]
    if secret_ids:
        fields.append("secrets")
    return fields, secret_ids


def interpret_world(cfg: AgentConfig, inp: WorldOrchestratorInput, result: DecisionResult) -> WorldOrchestratorPlan:
    """Port `group.py:direct()` overrides, owed replies, and multi-speaker chains up to `chain_max`."""
    cast_by_id, present, mention_arriving, remaining_absent, all_absent = _partition_cast(inp)
    present_ids = [entry.id for entry in present]
    present_set = set(present_ids)
    mention_arriving_ids = [entry.id for entry in mention_arriving]
    all_absent_set = {entry.id for entry in all_absent}
    allowed_speakers = (*present_ids, *mention_arriving_ids, NARRATOR_ID)

    turn_ans = _choice_answer(result, "turn_type")
    turn_type = turn_ans.choice if turn_ans and turn_ans.choice in WORLD_TURN_TYPES else "dialogue"

    sp_ans = _choice_answer(result, "speaker")
    speaker = sp_ans.choice if sp_ans and sp_ans.choice in allowed_speakers else NARRATOR_ID
    conf = float(sp_ans.confidence) if sp_ans else 0.0
    sp_probs = dict(sp_ans.probabilities) if sp_ans else {}
    why = "orchestrator"

    has_user_msg = bool(inp.user_message.strip())
    if speaker == NARRATOR_ID and mention_arriving_ids and has_user_msg:
        speaker = max(mention_arriving_ids, key=lambda cid: sp_probs.get(cid, 0.0))
        why = "arriving"

    seen = [entry.id for entry in remaining_absent if _noul(result, f"arrive__{entry.id}") >= ARRIVE_THRESHOLD]

    addressee: str | None = None
    addr_probs: dict[str, float] = {}
    addr_ans = _choice_answer(result, "addressee")
    if addr_ans is not None:
        addr_probs = dict(addr_ans.probabilities)
        if addr_ans.choice in cast_by_id and addr_ans.confidence >= ADDRESS_CONFIDENCE:
            addressee = addr_ans.choice

    if addressee is not None and addressee in all_absent_set and addressee not in seen:
        seen.append(addressee)

    new_arr = [cid for cid in seen if cid not in mention_arriving_ids]
    arriving_ids = [*mention_arriving_ids, *new_arr]
    arriving_set = set(arriving_ids)

    if speaker == NARRATOR_ID and new_arr and has_user_msg and addressee is None:
        speaker = new_arr[0]
        why = "arriving"

    named = [cid for cid in present_ids if mentioned(cast_by_id[cid].card, inp.user_message)] if has_user_msg else []
    if addressee is not None and speaker != addressee:
        speaker = addressee
        why = "addressee"
    elif (
        named
        and speaker not in named
        and conf < NAMING_CONFIDENCE_CUTOFF
        and why == "orchestrator"
        and addr_probs.get(GROUP_ID, 0.0) < GROUP_ADDRESSEE_CUTOFF
    ):
        speaker = named[0]
        why = "named"

    if inp.force_speaker and (
        inp.force_speaker in present_set or inp.force_speaker in arriving_set or inp.force_speaker == NARRATOR_ID
    ):
        speaker = inp.force_speaker
        why = "forced"

    if has_user_msg:
        if addressee is not None:
            raw_owed = [addressee]
        elif named and addr_probs.get(GROUP_ID, 0.0) < GROUP_ADDRESSEE_CUTOFF:
            raw_owed = list(named)
        else:
            raw_owed = []
    else:
        raw_owed = [cid for cid in inp.state.awaiting_reply if cid in cast_by_id]
    owed_ids = [cid for cid in dict.fromkeys(raw_owed) if cid != speaker]

    limit = max(1, inp.chain_max)
    chain: list[tuple[str, str]] = [(speaker, why)]
    chosen = {speaker}

    def _append_chain(cid: str, reason: str) -> None:
        if len(chain) < limit and cid in cast_by_id and cid not in chosen:
            chain.append((cid, reason))
            chosen.add(cid)

    for cid in owed_ids:
        _append_chain(cid, "owed_reply")
    for cid in arriving_ids:
        _append_chain(cid, "arriving")

    quiet_candidates = [
        cid
        for cid in present_ids
        if cid not in chosen
        and inp.state.silence.get(cid, 0) >= QUIET_TURNS
        and _noul(result, f"followup__{cid}") >= QUIET_THRESHOLD
    ]
    quiet_candidates.sort(
        key=lambda cid: (_noul(result, f"followup__{cid}"), inp.state.silence.get(cid, 0)), reverse=True
    )
    for cid in quiet_candidates:
        _append_chain(cid, "quiet_followup")

    candidate_cast_ids = [*present_ids, *arriving_ids]
    chain_candidates = [
        cid for cid in candidate_cast_ids if cid not in chosen and _noul(result, f"followup__{cid}") >= CHAIN_THRESHOLD
    ]
    chain_candidates.sort(key=lambda cid: _noul(result, f"followup__{cid}"), reverse=True)
    for cid in chain_candidates:
        _append_chain(cid, "chain_followup")

    secondary_candidates = [
        cid for cid in candidate_cast_ids if cid not in chosen and sp_probs.get(cid, 0.0) >= SECONDARY_SPEAKER_THRESHOLD
    ]
    secondary_candidates.sort(key=lambda cid: sp_probs.get(cid, 0.0), reverse=True)
    for cid in secondary_candidates:
        _append_chain(cid, "secondary")

    speakers: list[WorldPlannedSpeaker] = []
    for order, (cid, reason) in enumerate(chain):
        fields, secret_ids = _speaker_fields_and_secrets(cfg, cast_by_id, result, cid)
        speakers.append(
            WorldPlannedSpeaker(
                id=cid,
                kind="narrator" if cid == NARRATOR_ID else "character",
                sentences=cfg.sentences,
                order=order,
                reason=reason,
                entering=cid in arriving_set,
                card_fields=fields,
                secret_ids=secret_ids,
            )
        )

    lore_ids = list(
        dict.fromkeys(
            hit.entry.id
            for hit in inp.candidates
            if f"lore__{hit.entry.id}" in result.answers
            and _noul(result, f"lore__{hit.entry.id}") >= cfg.lore_threshold
        )
    )
    return WorldOrchestratorPlan(
        turn_type=turn_type,
        speakers=speakers,
        arriving_ids=arriving_ids,
        addressee=addressee,
        owed_ids=owed_ids,
        lore_entry_ids=lore_ids,
    )


def fallback_world_plan(cfg: AgentConfig) -> WorldOrchestratorPlan:
    """Used when the world Decisions call fails: narrator-only plan with core fields."""
    return WorldOrchestratorPlan(
        turn_type="dialogue",
        speakers=[
            WorldPlannedSpeaker(
                id=NARRATOR_ID,
                kind="narrator",
                sentences=cfg.sentences,
                order=0,
                reason="fallback",
                entering=False,
                card_fields=list(CORE_CARD_FIELDS),
            )
        ],
        fallback=True,
    )


async def run_world(
    ctx: AgentContext, cfg: AgentConfig, inp: WorldOrchestratorInput
) -> AgentResult[WorldOrchestratorPlan]:
    """Never raises (except cancellation): a failing call yields a narrator-only fallback plan and a `notice`."""
    questions = build_world_questions(cfg, inp, ctx.settings.decisions_max_questions)
    try:
        result = await ctx.llm.decide(AGENT_ID, cfg.model, build_world_state(cfg, inp), questions)
        plan = interpret_world(cfg, inp, result)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning("world orchestrator failed (%s); using narrator fallback", type(exc).__name__)
        detail = getattr(exc, "code", type(exc).__name__)
        return AgentResult(
            value=fallback_world_plan(cfg),
            notices=[Notice(code="orchestrator_fallback", agent=AGENT_ID, detail=str(detail))],
        )
    return AgentResult(value=plan, usage=[result.usage])
