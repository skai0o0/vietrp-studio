"""Bond Selector (architecture section 3.0): picks one drafted option per pair and merges it into `state.bonds`.

Merging never overwrites a field the card pins or the user edited by hand; it only fills gaps. A re-run triggered by
the Archivist (P4) may pass `overwrite_unpinned=True` to move agent-written fields, each change recorded with the
`seq` of the message that caused it.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult, Notice
from app.agents.bond_drafter import (
    FIELD_NAMES,
    PINNABLE,
    BondChange,
    BondFields,
    BondPair,
    BondRecord,
    DraftedBonds,
)
from app.agents.orchestrator import split_choice
from app.llm.decisions import Choice, Question
from app.llm.defaults import DEFAULT_MODELS
from app.prompts import render_prompt

logger = logging.getLogger(__name__)

AGENT_ID = "bond_selector"


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["bond_selector"]
    # Pairs per Decisions call; the rest take their first option (question budget, AGENTS.md section 4.4).
    max_pairs: int = Field(default=20, ge=1)
    max_opening_chars: int = Field(default=600, ge=1)


@dataclass(frozen=True, slots=True)
class SelectorInput:
    pairs: Sequence[BondPair]
    drafted: DraftedBonds
    opening: str = ""


def _summary(option: BondFields) -> str:
    return "; ".join(f"{k}: {v}" for k, v in option.as_strings().items())


def build_questions(cfg: AgentConfig, inp: SelectorInput, budget: int) -> dict[str, Question]:
    """One atomic `choice` per pair that has two or more options. Keys are `bond__<index>` (pair ids may hold any
    character)."""
    questions: dict[str, Question] = {}
    limit = min(cfg.max_pairs, budget)
    for index, pair in enumerate(inp.pairs):
        options = inp.drafted.options.get(pair.pair_id, [])
        if len(options) < 2 or len(questions) >= limit:
            continue
        instructions, _ = split_choice(
            render_prompt("bond_selector/q_bond.j2", character_name=pair.character_name, other_name=pair.other_name)
        )
        questions[f"bond__{index}"] = Choice(
            criteria={str(i + 1): _summary(option) for i, option in enumerate(options)}, instructions=instructions
        )
    return questions


def merge_bond(
    existing: BondRecord | None,
    pair: BondPair,
    proposal: BondFields,
    seq: int,
    *,
    overwrite_unpinned: bool = False,
) -> BondRecord:
    """Pinned values win and are recorded as pinned; other fields fill gaps (or, if asked, replace agent-written
    values). Fields the user edited (`manual`) are never touched."""
    record = (
        existing.model_copy(deep=True) if existing is not None else BondRecord(pair_id=pair.pair_id, label=pair.label)
    )
    record.label = pair.label
    current = record.fields.model_dump()
    new_values = proposal.model_dump()
    pinned = set(record.pinned)
    for name in PINNABLE:
        if name in pair.pinned:
            pinned.add(name)
            new_values[name] = pair.pinned[name]
    record.pinned = [n for n in FIELD_NAMES if n in pinned]
    for name in FIELD_NAMES:
        old, new = current[name], new_values[name]
        if name in record.manual or new == old:
            continue
        # closeness 0 is a real value but indistinguishable from "unset"; only a non-zero value fills a gap.
        has_value = bool(old) if name != "closeness" else old != 0
        if name in pinned:
            take = name in pair.pinned
        else:
            take = bool(new) if not has_value else overwrite_unpinned
        if take:
            current[name] = new
            record.changes.append(BondChange(seq=seq, field=name, old=str(old), new=str(new)))
    record.fields = BondFields.model_validate(current)
    return record


def apply_selection(
    existing: Mapping[str, BondRecord],
    pairs: Sequence[BondPair],
    selected: Mapping[str, BondFields],
    seq: int,
    *,
    overwrite_unpinned: bool = False,
) -> dict[str, BondRecord]:
    """New `state.bonds` content: every pair gets a record (pinned values alone if nothing was selected)."""
    out = dict(existing)
    for pair in pairs:
        out[pair.pair_id] = merge_bond(
            existing.get(pair.pair_id),
            pair,
            selected.get(pair.pair_id, BondFields()),
            seq,
            overwrite_unpinned=overwrite_unpinned,
        )
    return out


async def run(ctx: AgentContext, cfg: AgentConfig, inp: SelectorInput) -> AgentResult[dict[str, BondFields]]:
    """Pick one option per pair. A single option needs no question; if the Decisions call fails, the first option
    wins and a `bond_selector_fallback` notice is returned. Pairs without options are absent from the result."""
    picks: dict[str, BondFields] = {}
    for pair in inp.pairs:
        options = inp.drafted.options.get(pair.pair_id, [])
        if options:
            picks[pair.pair_id] = options[0]
    questions = build_questions(cfg, inp, ctx.settings.decisions_max_questions)
    if not questions:
        return AgentResult(value=picks)
    opening = render_prompt("bond_selector/state.j2", opening=inp.opening[: cfg.max_opening_chars]).strip()
    state = {"opening": opening or "-"}
    try:
        result = await ctx.llm.decide(AGENT_ID, cfg.model, state, questions)
    except Exception as exc:
        logger.warning("bond selector failed (%s); using first options", type(exc).__name__)
        detail = str(getattr(exc, "code", type(exc).__name__))
        return AgentResult(value=picks, notices=[Notice(code="bond_selector_fallback", agent=AGENT_ID, detail=detail)])
    for index, pair in enumerate(inp.pairs):
        key = f"bond__{index}"
        if key not in result.answers:
            continue
        options = inp.drafted.options[pair.pair_id]
        chosen = result.choice(key).choice
        if chosen.isdigit() and 1 <= int(chosen) <= len(options):
            picks[pair.pair_id] = options[int(chosen) - 1]
    return AgentResult(value=picks, usage=[result.usage])
