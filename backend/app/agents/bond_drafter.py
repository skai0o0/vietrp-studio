"""Bond Drafter (architecture section 3.0): proposes addressing and relationship options per pair.

One agent drafts, `bond_selector` picks. Fields the card pins (`addressing.user`, `relationships.user`, and the
`by_character` entries) are never drafted over: they are passed to the model as fixed and re-applied by
`bond_selector.merge_bond`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult, Notice
from app.formats.card import VietrpCard
from app.formats.persona import Persona
from app.llm.chat import ChatParams
from app.llm.client import LLMError
from app.llm.decisions import parse_json_object
from app.llm.defaults import DEFAULT_MODELS
from app.pipeline.prompt_assembler import BondView
from app.pipeline.world_assembly import WorldCastEntry
from app.prompts import render_prompt

logger = logging.getLogger(__name__)

AGENT_ID = "bond_drafter"
USER_ID = "user"
# Order of the bond fields in prompts and records.
FIELD_NAMES = ("addressing", "nickname", "relationship", "stance", "closeness", "history")
# Bond fields a card can pin, mapped to the card values that pin them.
PINNABLE = ("addressing", "relationship")
CLOSENESS_MIN = 0
CLOSENESS_MAX = 4  # architecture 3.0: closeness 0-4


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["bond_drafter"]
    # Options proposed per pair; the Selector picks one.
    options: int = Field(default=3, ge=1, le=6)
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1200, ge=1)
    # Longest text kept for any single bond field.
    max_field_chars: int = Field(default=200, ge=1)
    # Chars of the opening message shown to the model.
    max_opening_chars: int = Field(default=1200, ge=1)


class BondFields(BaseModel):
    addressing: str = ""
    nickname: str = ""
    relationship: str = ""
    stance: str = ""
    closeness: int = Field(default=0, ge=CLOSENESS_MIN, le=CLOSENESS_MAX)
    history: str = ""

    def as_strings(self) -> dict[str, str]:
        """Non-empty fields as strings, for the prompt layer."""
        out: dict[str, str] = {}
        for name in FIELD_NAMES:
            value = getattr(self, name)
            if name == "closeness":
                if self.closeness:
                    out[name] = str(self.closeness)
            elif value:
                out[name] = str(value)
        return out


class BondChange(BaseModel):
    seq: int
    field: str
    old: str
    new: str


class BondRecord(BaseModel):
    """One pair inside `chat.state.bonds[pair_id]`."""

    pair_id: str
    label: str
    fields: BondFields = Field(default_factory=BondFields)
    # Field names the card pinned. Never overwritten by agents.
    pinned: list[str] = Field(default_factory=list)
    # Who last set a field: names of fields the user edited by hand (agents then leave them alone).
    manual: list[str] = Field(default_factory=list)
    changes: list[BondChange] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BondPair:
    pair_id: str
    character_name: str
    other_name: str
    other_kind: Literal["persona", "character"]
    # Card-pinned values by bond field name ("addressing", "relationship").
    pinned: Mapping[str, str] = field(default_factory=dict)
    character_brief: str = ""
    other_brief: str = ""

    @property
    def label(self) -> str:
        return f"{self.character_name} ↔ {self.other_name}"


def user_pair(card: VietrpCard, character_id: str, persona: Persona | None, user_fallback: str) -> BondPair:
    """The single-chat pair: the card's character towards the player."""
    pinned: dict[str, str] = {}
    if card.addressing.user.strip():
        pinned["addressing"] = card.addressing.user.strip()
    if card.relationships.user.strip():
        pinned["relationship"] = card.relationships.user.strip()
    other_name = persona.name if persona is not None else user_fallback
    other_brief = ""
    if persona is not None:
        other_brief = "; ".join(x for x in (persona.gender, persona.personality, persona.background) if x)
    return BondPair(
        pair_id=f"{character_id}:{USER_ID}",
        character_name=card.name,
        other_name=other_name,
        other_kind="persona",
        pinned=pinned,
        character_brief=card.tagline,
        other_brief=other_brief,
    )


def world_pairs(cast: Sequence[WorldCastEntry], persona: Persona | None, user_fallback: str) -> list[BondPair]:
    """World-chat pairs: `{cid}:user` for every cast member and `{a.id}:{b.id}` for every ordered `a != b`."""
    pairs: list[BondPair] = [user_pair(entry.card, entry.id, persona, user_fallback) for entry in cast]
    for a in cast:
        for b in cast:
            if a.id == b.id:
                continue
            pinned: dict[str, str] = {}
            addr = a.card.addressing.by_character.get(b.id, "").strip()
            if addr:
                pinned["addressing"] = addr
            rel = a.card.relationships.by_character.get(b.id, "").strip()
            if rel:
                pinned["relationship"] = rel
            pairs.append(
                BondPair(
                    pair_id=f"{a.id}:{b.id}",
                    character_name=a.card.name,
                    other_name=b.card.name,
                    other_kind="character",
                    pinned=pinned,
                    character_brief=a.card.tagline,
                    other_brief=b.card.tagline,
                )
            )
    return pairs


@dataclass(frozen=True, slots=True)
class DrafterInput:
    pairs: Sequence[BondPair]
    # The greeting or opening the chat starts from; it can imply that the pair already know each other.
    opening: str = ""


@dataclass(slots=True)
class DraftedBonds:
    """Options per pair id, in the model's order. A pair with no usable option has an empty list."""

    options: dict[str, list[BondFields]] = field(default_factory=dict)


def _text(value: Any, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def parse_option(raw: Any, cfg: AgentConfig) -> BondFields | None:
    if not isinstance(raw, dict):
        return None
    closeness = raw.get("closeness")
    level = closeness if isinstance(closeness, int | float) and not isinstance(closeness, bool) else 0
    option = BondFields(
        addressing=_text(raw.get("addressing"), cfg.max_field_chars),
        nickname=_text(raw.get("nickname"), cfg.max_field_chars),
        relationship=_text(raw.get("relationship"), cfg.max_field_chars),
        stance=_text(raw.get("stance"), cfg.max_field_chars),
        closeness=min(CLOSENESS_MAX, max(CLOSENESS_MIN, round(level))),
        history=_text(raw.get("history"), cfg.max_field_chars),
    )
    return option if option.as_strings() else None


def parse_reply(text: str, pairs: Sequence[BondPair], cfg: AgentConfig) -> DraftedBonds:
    """Lenient: unknown pairs and unusable options are skipped. Raises `LLMError` when the reply is not JSON."""
    parsed = parse_json_object(text)
    raw_pairs = parsed.get("pairs")
    drafted = DraftedBonds(options={pair.pair_id: [] for pair in pairs})
    if not isinstance(raw_pairs, dict):
        return drafted
    for pair in pairs:
        raw_list = raw_pairs.get(pair.pair_id)
        if not isinstance(raw_list, list):
            continue
        options = [o for o in (parse_option(raw, cfg) for raw in raw_list) if o is not None]
        drafted.options[pair.pair_id] = options[: cfg.options]
    return drafted


async def run(ctx: AgentContext, cfg: AgentConfig, inp: DrafterInput) -> AgentResult[DraftedBonds]:
    """Chat JSON call. A malformed reply gives empty options plus a `bond_drafter_malformed` notice, not an error.
    Transport failures propagate: wrap the call in `run_non_critical`."""
    pairs = list(inp.pairs)
    if not pairs:
        return AgentResult(value=DraftedBonds())
    system = render_prompt("bond_drafter/system.j2", options=cfg.options)
    briefs = [
        {
            "pair_id": p.pair_id,
            "character_name": p.character_name,
            "other_name": p.other_name,
            "other_kind": p.other_kind,
            "character_brief": p.character_brief,
            "other_brief": p.other_brief,
            "pinned": dict(p.pinned),
        }
        for p in pairs
    ]
    user = render_prompt("bond_drafter/user.j2", pairs=briefs, opening=inp.opening[: cfg.max_opening_chars])
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    max_tokens = min(4096, max(cfg.max_tokens, len(pairs) * 180))
    params = ChatParams(temperature=cfg.temperature, max_tokens=max_tokens, reasoning="off")
    text, usage = await ctx.llm.complete(AGENT_ID, cfg.model, messages, params)
    try:
        drafted = parse_reply(text, pairs, cfg)
    except LLMError:
        logger.warning("bond drafter reply was not valid JSON")
        return AgentResult(
            value=DraftedBonds(options={p.pair_id: [] for p in pairs}),
            usage=[usage],
            notices=[Notice(code="bond_drafter_malformed", agent=AGENT_ID, detail="reply is not valid JSON")],
        )
    return AgentResult(value=drafted, usage=[usage])


def bond_views(records: Mapping[str, BondRecord]) -> list[BondView]:
    """Prompt-layer view. Pinned fields are left out: the card layer already carries them."""
    views: list[BondView] = []
    for record in records.values():
        fields = {k: v for k, v in record.fields.as_strings().items() if k not in record.pinned}
        if fields:
            views.append(BondView(pair=record.label, fields=fields))
    return views


def bonds_for_speaker(
    records: Mapping[str, BondRecord],
    speaker_id: str,
    present_ids: Sequence[str] | None = None,
) -> list[BondView]:
    """Prompt-layer views filtered to pairs involving `speaker_id` (or active pairs for `narrator`/`group`)."""
    if speaker_id in ("narrator", "group"):
        if present_ids is None:
            return bond_views(records)
        allowed = set(present_ids) | {USER_ID}
        filtered = {
            pid: rec
            for pid, rec in records.items()
            if (parts := pid.partition(":"))[1] and parts[0] in allowed and parts[2] in allowed
        }
        return bond_views(filtered)
    allowed_char = (set(present_ids) | {speaker_id, USER_ID}) if present_ids is not None else None
    filtered_char: dict[str, BondRecord] = {}
    for pid, rec in records.items():
        left, sep, right = pid.partition(":")
        if not sep or speaker_id not in (left, right):
            continue
        if allowed_char is not None and (left not in allowed_char or right not in allowed_char):
            continue
        filtered_char[pid] = rec
    return bond_views(filtered_char)
