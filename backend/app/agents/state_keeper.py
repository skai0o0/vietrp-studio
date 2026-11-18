"""State Keeper (architecture §3, agent 4; world chat only): updates structured `WorldState`.

Runs Decisions (presence with hysteresis, nearby location, tension, interject candidates) and Extractions (time,
preserving the Vietnamese weekday via `keep_day`) concurrently. Non-critical: an Extractions error keeps the old
time with a `state_keeper_time_failed` notice without dropping Decisions updates, and a Decisions error keeps the old
structured state with a `state_keeper_failed` notice.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult, Notice, _safe_detail
from app.agents.orchestrator import nearby_locations, split_choice
from app.core.config import (
    CHAIN_THRESHOLD,
    LOCATION_CONFIDENCE,
    OWED_THRESHOLD,
    PRESENCE_ENTER_THRESHOLD,
    PRESENCE_STAY_THRESHOLD,
    QUIET_THRESHOLD,
    QUIET_TURNS,
    TIME_CONFIDENCE,
)
from app.formats.world import VietrpWorld
from app.llm.decisions import Choice, ChoiceAnswer, DecisionResult, Noul, NoulAnswer, Question, Score, ScoreAnswer
from app.llm.defaults import DEFAULT_EXTRACTIONS_MODEL, DEFAULT_MODELS
from app.llm.extractions import ExtractionResult
from app.llm.extractions import Field as ExtractionField
from app.llm.usage import Usage
from app.pipeline.world_assembly import WorldCastEntry, location_path
from app.prompts import render_prompt
from app.schemas.world_state import WorldState

logger = logging.getLogger(__name__)

AGENT_ID = "state_keeper"
TENSION_MAX = 4
_DAY_RE = re.compile(r"(thứ\s+(?:hai|ba|tư|năm|sáu|bảy|\d)|chủ\s+nhật)", re.IGNORECASE)


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["state_keeper"]
    extract_model: str = DEFAULT_EXTRACTIONS_MODEL
    # Last N lines shown to Decisions/Extractions (reference group.py:update_state uses 3).
    recent_lines: int = Field(default=3, ge=1)
    max_line_chars: int = Field(default=600, ge=1)


@dataclass(frozen=True, slots=True)
class StateKeeperInput:
    world: VietrpWorld
    cast: Sequence[WorldCastEntry]
    state: WorldState
    user_name: str
    recent_lines: Sequence[str]
    speakers_this_turn: Sequence[str]
    owed_ids: Sequence[str] = ()
    arriving_ids: Sequence[str] = ()


class StateKeeperOutcome(BaseModel):
    state: WorldState
    changed: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)
    next_speaker: str | None = None
    next_reason: str | None = None


def keep_day(old: str, new: str) -> str:
    """Port of `group.py:keep_day`: keep the Vietnamese weekday from `old` if `new` omits it."""
    norm_new = unicodedata.normalize("NFC", new)
    norm_old = unicodedata.normalize("NFC", old)
    if _DAY_RE.search(norm_new):
        return norm_new.strip()
    match = _DAY_RE.search(norm_old)
    if match is None:
        return norm_new.strip()
    stripped = norm_new.strip()
    return f"{stripped} {match.group(0)}" if stripped else match.group(0)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def build_state_text(cfg: AgentConfig, inp: StateKeeperInput) -> str:
    cast_by_id = {entry.id: entry for entry in inp.cast}
    present_names = [cast_by_id[cid].card.name for cid in dict.fromkeys(inp.state.present_ids) if cid in cast_by_id]
    lines = [_truncate(line, cfg.max_line_chars) for line in inp.recent_lines[-cfg.recent_lines :]]
    return render_prompt(
        "state_keeper/state.j2",
        world_name=inp.world.name,
        location_path=location_path(inp.world.locations, inp.state.location_id),
        time=inp.state.time.strip(),
        tension=max(0, min(TENSION_MAX, inp.state.tension)),
        user=inp.user_name,
        present=present_names,
        recent=lines,
    )


def build_questions(cfg: AgentConfig, inp: StateKeeperInput, budget: int) -> dict[str, Question]:
    """Build State Keeper Decisions questions, strictly bounded by `budget` and `nearby_locations`."""
    if budget <= 0:
        return {}
    questions: dict[str, Question] = {}

    def _add(key: str, question: Question) -> None:
        if len(questions) < budget:
            questions[key] = question

    for entry in inp.cast:
        if len(questions) >= budget:
            break
        _add(
            f"present__{entry.id}",
            Noul(
                instructions=render_prompt(
                    "state_keeper/q_present.j2",
                    name=entry.card.name,
                    tagline=_one_line(entry.card.tagline),
                )
            ),
        )

    nearby = nearby_locations(inp.world.locations, inp.state.location_id)
    if nearby and len(questions) < budget:
        loc_vars = [
            {"id": loc.id, "name": _one_line(loc.name), "description": _one_line(loc.description)} for loc in nearby
        ]
        loc_instr, loc_criteria = split_choice(render_prompt("state_keeper/q_location.j2", locations=loc_vars))
        _add("location", Choice(criteria=loc_criteria, instructions=loc_instr))

    if len(questions) < budget:
        tens_instr, tens_criteria = split_choice(render_prompt("state_keeper/q_tension.j2"))
        _add("tension", Score(criteria=list(tens_criteria.values()), instructions=tens_instr))

    last_speaker = inp.speakers_this_turn[-1] if inp.speakers_this_turn else None
    for entry in inp.cast:
        if len(questions) >= budget:
            break
        if entry.id == last_speaker:
            continue
        _add(
            f"interject__{entry.id}",
            Noul(
                instructions=render_prompt(
                    "state_keeper/q_interject.j2",
                    name=entry.card.name,
                    tagline=_one_line(entry.card.tagline),
                    user=inp.user_name,
                )
            ),
        )
    return questions


def _noul(result: DecisionResult, key: str, default: float = 0.0) -> float:
    answer = result.answers.get(key)
    return answer.p if isinstance(answer, NoulAnswer) else default


def _choice_answer(result: DecisionResult, key: str) -> ChoiceAnswer | None:
    answer = result.answers.get(key)
    return answer if isinstance(answer, ChoiceAnswer) else None


def interpret(
    inp: StateKeeperInput,
    dec_result: DecisionResult | None,
    ext_result: ExtractionResult | None,
) -> StateKeeperOutcome:
    """Apply Decisions and Extractions results onto a deep copy of `inp.state`."""
    cast_by_id = {entry.id: entry for entry in inp.cast}
    confidence: dict[str, float] = {}
    changed: list[str] = []

    new_state = inp.state.model_copy(deep=True)
    next_speaker: str | None = None
    next_reason: str | None = None

    if dec_result is not None:
        prev_present = set(inp.state.present_ids)
        arriving_set = set(inp.arriving_ids)
        present_after: set[str] = set()
        for entry in inp.cast:
            key = f"present__{entry.id}"
            p = _noul(dec_result, key, default=1.0 if entry.id in prev_present else 0.0)
            confidence[key] = round(p, 4)
            threshold = (
                PRESENCE_STAY_THRESHOLD
                if (entry.id in prev_present or entry.id in arriving_set)
                else PRESENCE_ENTER_THRESHOLD
            )
            if p >= threshold:
                present_after.add(entry.id)

        new_present = [
            cid for cid in dict.fromkeys(inp.state.present_ids) if cid in present_after and cid in cast_by_id
        ]
        new_present.extend(entry.id for entry in inp.cast if entry.id in present_after and entry.id not in prev_present)
        if new_present != inp.state.present_ids:
            changed.append("present_ids")
        new_state.present_ids = new_present

        nearby_ids = {loc.id for loc in nearby_locations(inp.world.locations, inp.state.location_id)}
        new_location = inp.state.location_id
        loc_ans = _choice_answer(dec_result, "location")
        if loc_ans is not None:
            confidence["location_id"] = round(loc_ans.confidence, 4)
            if loc_ans.confidence >= LOCATION_CONFIDENCE and loc_ans.choice in nearby_ids:
                new_location = loc_ans.choice
        if new_location != inp.state.location_id:
            changed.append("location_id")
        new_state.location_id = new_location

        new_tension = inp.state.tension
        tens_ans = dec_result.answers.get("tension")
        if isinstance(tens_ans, ScoreAnswer):
            new_tension = max(0, min(TENSION_MAX, int(round(tens_ans.score))))
        if new_tension != inp.state.tension:
            changed.append("tension")
        new_state.tension = new_tension

        new_present_set = set(new_present)
        spoken_set = set(inp.speakers_this_turn)
        fresh = [cid for cid in new_present if cid not in prev_present and cid not in spoken_set]
        new_awaiting = list(
            dict.fromkeys([cid for cid in inp.owed_ids if cid in new_present_set and cid not in spoken_set] + fresh)
        )
        if new_awaiting != inp.state.awaiting_reply:
            changed.append("awaiting_reply")
        new_state.awaiting_reply = new_awaiting

        new_silence = {cid: (0 if cid in spoken_set else inp.state.silence.get(cid, 0) + 1) for cid in new_present}
        if new_silence != inp.state.silence:
            changed.append("silence")
        new_state.silence = new_silence

        interject: dict[str, float] = {}
        for entry in inp.cast:
            key = f"interject__{entry.id}"
            if key in dec_result.answers:
                p = _noul(dec_result, key)
                confidence[key] = round(p, 4)
                if entry.id in new_present_set:
                    interject[entry.id] = p

        owed_ok = [cid for cid in new_awaiting if cid in fresh or interject.get(cid, 0.0) >= OWED_THRESHOLD]
        if owed_ok:
            next_speaker = max(owed_ok, key=lambda cid: interject.get(cid, 0.0))
            next_reason = "arrived_silent" if next_speaker in fresh else "owed_reply"
        else:
            eligible = [
                cid
                for cid, p in interject.items()
                if p >= (QUIET_THRESHOLD if new_silence.get(cid, 0) >= QUIET_TURNS else CHAIN_THRESHOLD)
            ]
            if eligible:
                next_speaker = max(eligible, key=lambda cid: interject[cid])
                next_reason = "quiet_followup" if new_silence.get(next_speaker, 0) >= QUIET_TURNS else "chain_reaction"

    if ext_result is not None:
        tg = ext_result.values.get("time")
        if tg is not None:
            confidence["time"] = round(tg.confidence, 4)
            if tg.value.strip() and tg.confidence >= TIME_CONFIDENCE:
                new_time = keep_day(inp.state.time, tg.value)
                if new_time != inp.state.time:
                    changed.append("time")
                new_state.time = new_time

    return StateKeeperOutcome(
        state=new_state,
        changed=changed,
        confidence=confidence,
        next_speaker=next_speaker,
        next_reason=next_reason,
    )


async def run(ctx: AgentContext, cfg: AgentConfig, inp: StateKeeperInput) -> AgentResult[StateKeeperOutcome]:
    """Run Decisions and Extractions concurrently; non-critical errors become notices and preserve old state."""
    state_text = build_state_text(cfg, inp)
    questions = build_questions(cfg, inp, ctx.settings.decisions_max_questions)
    time_field = {"time": ExtractionField(type="text", instructions=render_prompt("state_keeper/extract_time.j2"))}

    async def _no_decisions() -> DecisionResult | None:
        return None

    dec_coro = ctx.llm.decide(AGENT_ID, cfg.model, {"content": state_text}, questions) if questions else _no_decisions()
    ext_coro = ctx.llm.extract(AGENT_ID, cfg.extract_model, state_text, time_field)
    dec_res, ext_res = await asyncio.gather(dec_coro, ext_coro, return_exceptions=True)

    if isinstance(dec_res, BaseException) and not isinstance(dec_res, Exception):
        raise dec_res
    if isinstance(ext_res, BaseException) and not isinstance(ext_res, Exception):
        raise ext_res

    usage: list[Usage] = []
    notices: list[Notice] = []
    dec_result: DecisionResult | None = None
    ext_result: ExtractionResult | None = None

    if isinstance(dec_res, Exception):
        detail = _safe_detail(dec_res)
        logger.warning("state_keeper decisions failed (%s); preserving structured state", detail)
        notices.append(Notice(code="state_keeper_failed", agent=AGENT_ID, detail=detail))
    elif dec_res is not None:
        dec_result = dec_res
        usage.append(dec_res.usage)

    if isinstance(ext_res, Exception):
        detail = _safe_detail(ext_res)
        logger.warning("state_keeper time extraction failed (%s); keeping previous time", detail)
        notices.append(Notice(code="state_keeper_time_failed", agent=AGENT_ID, detail=detail))
    else:
        ext_result = ext_res
        usage.append(ext_res.usage)

    outcome = interpret(inp, dec_result, ext_result)
    return AgentResult(value=outcome, usage=usage, notices=notices)
