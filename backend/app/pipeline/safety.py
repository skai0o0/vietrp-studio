"""Minor-safety rules (AGENTS.md section 2.1). This module is the only home of the injection logic.

The rule text itself lives in `prompts/_shared/minor_rule.j2`; this module refuses to run without it.
Nothing a user controls (presets, /cmd, prefill, NSFW setting) is able to remove or reorder the rule:
`apply` always strips look-alike layers and appends the rule as the final system layer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.core.errors import AppError
from app.formats.card import VietrpCard
from app.formats.common import normalize_tag
from app.prompts import render_prompt

# Ages below this are minors.
ADULT_AGE = 18
MINOR_RULE_TEMPLATE = "_shared/minor_rule.j2"
MINOR_RULE_LAYER = "minor_rule"
CREATOR_RULE_TEMPLATE = "_shared/creator_minor_rule.j2"


class SafetyConfigError(RuntimeError):
    """The safety rule cannot be rendered. Generation must not continue without it."""


@dataclass(frozen=True, slots=True)
class CastMember:
    """A character present in the scene. NPCs created with /addnpc are cast members with `is_npc=True`."""

    name: str
    age: int | None
    is_npc: bool = False


@dataclass(frozen=True, slots=True)
class PromptLayer:
    name: str
    role: Literal["system", "user", "assistant"]
    text: str


def cast_from_card(card: VietrpCard) -> CastMember:
    return CastMember(name=card.name, age=card.age)


def card_has_minor(card: VietrpCard) -> bool:
    return card.age is not None and card.age < ADULT_AGE


# `nsfw`, `nsfw_x`, `nsfw-x`, `nsfw x`, `18+`, `r18`, `r-18`, `adult` after normalisation.
_NSFW_TAG = re.compile(r"^(?:nsfw(?:[_\- ].*)?|18\+|r-?18|adult)$")


def is_nsfw_tagged(tags: Sequence[str]) -> bool:
    return any(_NSFW_TAG.match(normalize_tag(tag).lower()) for tag in tags)


def public_nsfw_blocked(card: VietrpCard, visibility: str) -> bool:
    """True when a public card must not carry an NSFW tag: unknown age counts as a possible minor."""
    return visibility == "public" and (card.age is None or card_has_minor(card)) and is_nsfw_tagged(card.tags)


def is_minor(member: CastMember) -> bool:
    """Unknown-age NPCs are treated as minors (conservative); unknown-age cast members are rejected earlier."""
    if member.age is None:
        return member.is_npc
    return member.age < ADULT_AGE


def assert_cast_usable(cast: Iterable[CastMember]) -> None:
    """A chat cannot start or continue while a (non-NPC) character has no age."""
    for member in cast:
        if member.age is None and not member.is_npc:
            raise AppError("age_required", f"Character '{member.name}' has no age set", 422)


def minor_rule(cast: Iterable[CastMember]) -> str | None:
    """The Vietnamese hard rule when any present character is under 18, else None."""
    names = [member.name for member in cast if is_minor(member)]
    if not names:
        return None
    try:
        text = render_prompt(MINOR_RULE_TEMPLATE, names=list(dict.fromkeys(names)))
    except Exception as exc:  # missing/broken template
        raise SafetyConfigError("minor safety rule template cannot be rendered") from exc
    if not text.strip():
        raise SafetyConfigError("minor safety rule template is empty")
    return text


def creator_rule() -> str:
    """The hard rule for the Creator: the card's age is unknown while drafting, so it is always sent."""
    try:
        text = render_prompt(CREATOR_RULE_TEMPLATE)
    except Exception as exc:  # missing/broken template
        raise SafetyConfigError("creator safety rule template cannot be rendered") from exc
    if not text.strip():
        raise SafetyConfigError("creator safety rule template is empty")
    return text


def apply(layers: Sequence[PromptLayer], cast: Iterable[CastMember], settings: Any = None) -> list[PromptLayer]:
    """Return `layers` with the minor rule as the last system layer (when needed).

    `settings` is accepted so callers pass the same object everywhere, but it is deliberately ignored:
    no setting can switch the rule off. Any incoming layer named like the rule is dropped first.
    """
    del settings
    members = list(cast)
    assert_cast_usable(members)
    kept = [layer for layer in layers if layer.name != MINOR_RULE_LAYER]
    rule = minor_rule(members)
    if rule is None:
        return kept
    last_system = max((i for i, layer in enumerate(kept) if layer.role == "system"), default=-1)
    rule_layer = PromptLayer(name=MINOR_RULE_LAYER, role="system", text=rule)
    # Everything after the last system layer (history, prefill) stays after the rule.
    return [*kept[: last_system + 1], rule_layer, *kept[last_system + 1 :]]


def verify(layers: Sequence[PromptLayer], cast: Iterable[CastMember]) -> None:
    """Defence in depth: raise if the rule is required but absent or not the last system layer."""
    members = list(cast)
    rule = minor_rule(members)
    if rule is None:
        return
    system = [layer for layer in layers if layer.role == "system"]
    if not system or system[-1].name != MINOR_RULE_LAYER or system[-1].text != rule:
        raise SafetyConfigError("minor safety rule is missing, altered, or not the last system layer")
