"""Layered prompt assembly (architecture section 5.1). Pure: plain inputs in, `AssembledPrompt` out.

Order of system layers: preset system, NSFW text, lore (before_char), card, lore (after_char), persona,
bonds, memory (summary/events), `/cmd` instruction, and last the minor-safety rule (see `safety.apply`).
Then the recent window (newest messages that fit the budget) and the optional prefill.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.formats.card import VietrpCard
from app.formats.persona import Persona
from app.llm.config import LLMConfig
from app.llm.tokenizer import CorrectionTable, count_text
from app.pipeline import safety
from app.pipeline.commands import ParsedInput
from app.pipeline.context_budget import BudgetSettings
from app.pipeline.lorebook import LoreHit, order_by_position
from app.pipeline.safety import CastMember, PromptLayer
from app.prompts import render_prompt
from app.prompts.presets import PresetLayers, nsfw_text, substitute_placeholders, system_text

# Card fields the Orchestrator may select. Secrets are only sent when named explicitly.
CARD_FIELDS = (
    "appearance",
    "personality",
    "backstory",
    "goals",
    "limits",
    "speech",
    "addressing",
    "relationships",
    "extras",
    "secrets",
)
DEFAULT_CARD_FIELDS = frozenset(CARD_FIELDS) - {"secrets"}
# Name used in templates when no persona is selected.
FALLBACK_USER_NAME = "người chơi"


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class BondView:
    """One pair's bond, flattened for the prompt. Keys: addressing, nickname, relationship,
    stance, closeness, history."""

    pair: str
    fields: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class AssemblyInput:
    card: VietrpCard
    messages: Sequence[HistoryMessage]
    model: str
    persona: Persona | None = None
    bonds: Sequence[BondView] = ()
    lore: Sequence[LoreHit] = ()
    summary: str = ""
    events: Sequence[str] = ()
    npcs: Sequence[CastMember] = ()
    card_fields: Collection[str] | None = None
    preset: PresetLayers = field(default_factory=PresetLayers)
    nsfw: bool = False
    command: ParsedInput | None = None
    prefill: str | None = None
    # True when the Orchestrator picked the narrator: adds the narrator voice layer.
    narrator: bool = False
    budget: BudgetSettings = field(default_factory=BudgetSettings)
    corrections: CorrectionTable = field(default_factory=CorrectionTable)


@dataclass(frozen=True, slots=True)
class AssembledLayer:
    name: str
    tokens: int
    text: str


@dataclass(frozen=True, slots=True)
class AssembledPrompt:
    messages: list[dict[str, str]]
    layers: list[AssembledLayer]
    total_tokens: int
    # Messages left out of the recent window because they did not fit.
    history_dropped: int = 0
    # True when the fixed layers plus the newest message alone exceed the budget.
    over_budget: bool = False


def _card_view(card: VietrpCard, selected: Collection[str]) -> dict[str, Any]:
    view: dict[str, Any] = {
        "appearance": "",
        "personality": "",
        "backstory": "",
        "goals": "",
        "limits": [],
        "speech": None,
        "addressing": None,
        "relationships": None,
        "extras": {},
        "secrets": [],
    }
    for key in CARD_FIELDS:
        if key in selected:
            view[key] = getattr(card, key)
    return view


def _lore_text(hits: Sequence[LoreHit]) -> str:
    if not hits:
        return ""
    entries = [{"title": hit.entry.title, "content": hit.entry.content} for hit in hits]
    return render_prompt("_shared/lore.j2", entries=entries)


def _system_layers(data: AssemblyInput, user_name: str) -> list[PromptLayer]:
    card = data.card
    layers = [PromptLayer("system", "system", system_text(data.preset, char=card.name, user=user_name))]
    if data.nsfw:
        layers.append(PromptLayer("nsfw", "system", nsfw_text(data.preset, char=card.name, user=user_name)))
    before, after = order_by_position(data.lore)
    selected = DEFAULT_CARD_FIELDS if data.card_fields is None else set(data.card_fields)
    card_text = substitute_placeholders(
        render_prompt(
            "_shared/card.j2",
            name=card.name,
            age=card.age,
            aliases=card.aliases,
            user_name=user_name,
            f=_card_view(card, selected),
        ),
        char=card.name,
        user=user_name,
    )
    lore_before = substitute_placeholders(_lore_text(before), char=card.name, user=user_name)
    lore_after = substitute_placeholders(_lore_text(after), char=card.name, user=user_name)
    candidates: list[tuple[str, str]] = [
        ("lore_before", lore_before),
        ("card", card_text),
        ("lore_after", lore_after),
    ]
    if data.persona is not None:
        persona_vars = data.persona.model_dump(exclude={"format", "spec_version"})
        persona_text = substitute_placeholders(
            render_prompt("_shared/persona.j2", **persona_vars),
            char=card.name,
            user=user_name,
        )
        candidates.append(("persona", persona_text))
    if data.bonds:
        bonds = [{"pair": bond.pair, "fields": dict(bond.fields)} for bond in data.bonds]
        bonds_text = substitute_placeholders(
            render_prompt("_shared/bonds.j2", bonds=bonds),
            char=card.name,
            user=user_name,
        )
        candidates.append(("bonds", bonds_text))
    if data.summary.strip() or data.events:
        memory = substitute_placeholders(
            render_prompt("_shared/memory.j2", summary=data.summary.strip(), events=list(data.events)),
            char=card.name,
            user=user_name,
        )
        candidates.append(("memory", memory))
    if data.command is not None and data.command.kind == "cmd" and data.command.instruction:
        instruction = substitute_placeholders(data.command.instruction, char=card.name, user=user_name)
        candidates.append(("cmd_instruction", render_prompt("_shared/cmd_instruction.j2", instruction=instruction)))
    if data.narrator:
        candidates.append(("narrator", render_prompt("_shared/narrator.j2", char=card.name, user=user_name)))
    layers.extend(PromptLayer(name, "system", text) for name, text in candidates if text)
    return layers


def cast_of(data: AssemblyInput) -> list[CastMember]:
    """Everyone present: the card, the persona (when its age is known) and temporary NPCs."""
    cast = [safety.cast_from_card(data.card)]
    if data.persona is not None and data.persona.age is not None:
        cast.append(CastMember(name=data.persona.name, age=data.persona.age))
    cast.extend(data.npcs)
    return cast


def assemble(data: AssemblyInput) -> AssembledPrompt:
    """Build the prompt. Raises `AppError("age_required")` when a character has no age."""
    cast = cast_of(data)
    safety.assert_cast_usable(cast)
    user_name = data.persona.name if data.persona is not None else FALLBACK_USER_NAME
    system_layers = safety.apply(_system_layers(data, user_name), cast, None)

    overhead = LLMConfig().tokens_per_message
    factor = data.corrections.factor(data.model)

    def tokens_of(text: str) -> int:
        return math.ceil(count_text(text) * factor)

    def cost(text: str) -> int:
        return math.ceil((count_text(text) + overhead) * factor)

    raw_messages = [
        HistoryMessage(
            m.role,
            substitute_placeholders(m.content, char=data.card.name, user=user_name),
        )
        for m in data.messages
    ]
    prefill = substitute_placeholders((data.prefill or "").strip(), char=data.card.name, user=user_name)
    fixed = sum(cost(layer.text) for layer in system_layers) + (cost(prefill) if prefill else 0)
    remaining = data.budget.prompt_budget - fixed
    kept: list[HistoryMessage] = []
    for message in reversed(raw_messages):
        message_cost = cost(message.content)
        # The newest message is always kept, even when it alone overflows the budget.
        if kept and message_cost > remaining:
            break
        remaining -= message_cost
        kept.append(message)
    kept.reverse()

    final_layers: list[PromptLayer] = [*system_layers]
    final_layers.extend(PromptLayer("history", message.role, message.content) for message in kept)
    if prefill:
        final_layers.append(PromptLayer("prefill", "assistant", prefill))
    safety.verify(final_layers, cast)

    inspector = [AssembledLayer(layer.name, tokens_of(layer.text), layer.text) for layer in system_layers]
    if kept:
        history_text = "\n\n".join(f"{message.role}: {message.content}" for message in kept)
        inspector.append(AssembledLayer("history", sum(tokens_of(m.content) for m in kept), history_text))
    if prefill:
        inspector.append(AssembledLayer("prefill", tokens_of(prefill), prefill))
    return AssembledPrompt(
        messages=[{"role": layer.role, "content": layer.text} for layer in final_layers],
        layers=inspector,
        total_tokens=sum(cost(layer.text) for layer in final_layers),
        history_dropped=len(raw_messages) - len(kept),
        over_budget=remaining < 0,
    )
