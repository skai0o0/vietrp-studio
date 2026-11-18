"""Layered prompt assembly for world chats (architecture §4.2, §4.6, §5.2; AGENTS §2.1, §4.5).

Pure: plain inputs in, `AssembledPrompt` out. Mirrors `prompt_assembler.assemble` for token
budgeting and safety guarantees while adding world rules, location tree path, visible `<scene>`
state, present/arriving cast, world speaker roles, and `<scene>` output instructions.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from app.formats.card import VietrpCard
from app.formats.persona import Persona
from app.formats.world import Location, VietrpWorld
from app.llm.config import LLMConfig
from app.llm.tokenizer import CorrectionTable, count_text
from app.pipeline import safety
from app.pipeline.commands import ParsedInput
from app.pipeline.context_budget import BudgetSettings
from app.pipeline.lorebook import LoreHit, order_by_position
from app.pipeline.prompt_assembler import (
    CARD_FIELDS,
    DEFAULT_CARD_FIELDS,
    FALLBACK_USER_NAME,
    AssembledLayer,
    AssembledPrompt,
    BondView,
    HistoryMessage,
)
from app.pipeline.safety import CastMember, PromptLayer
from app.pipeline.scene_parser import visible_scene
from app.prompts import render_prompt
from app.prompts.presets import PresetLayers, nsfw_text, substitute_placeholders, system_text
from app.schemas.chat import GroupWriteMode
from app.schemas.world_state import SceneState

NARRATOR_SPEAKER_ID = "narrator"
NARRATOR_CARD_FIELDS = frozenset({"speech", "addressing", "relationships"})


@dataclass(frozen=True, slots=True)
class WorldCastEntry:
    """One character in the world chat's cast, pairing its short slug id with its card."""

    id: str
    card: VietrpCard


@dataclass(frozen=True, slots=True)
class WorldAssemblyInput:
    world: VietrpWorld
    cast: Sequence[WorldCastEntry]
    present_ids: Sequence[str]
    speaker_id: str
    messages: Sequence[HistoryMessage]
    model: str
    arriving_ids: Sequence[str] = ()
    location_id: str = ""
    time: str = ""
    tension: int = 0
    scene: SceneState | None = None
    player_role: str = ""
    persona: Persona | None = None
    bonds: Sequence[BondView] = ()
    lore: Sequence[LoreHit] = ()
    summary: str = ""
    events: Sequence[str] = ()
    npcs: Sequence[CastMember] = ()
    card_fields: Collection[str] | None = None
    write_mode: GroupWriteMode = "per_character"
    entering: bool = False
    preset: PresetLayers = field(default_factory=PresetLayers)
    nsfw: bool = False
    command: ParsedInput | None = None
    prefill: str | None = None
    budget: BudgetSettings = field(default_factory=BudgetSettings)
    corrections: CorrectionTable = field(default_factory=CorrectionTable)
    safety_cast_ids: Collection[str] = ()


def location_path(locations: Sequence[Location], location_id: str) -> str:
    """Walk `parent_id` up to root (with cycle guard) and format as `'A › B › C'`."""
    if not location_id:
        return ""
    by_id = {loc.id: loc for loc in locations}
    current = by_id.get(location_id)
    if current is None:
        return location_id
    names: list[str] = []
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        names.append(current.name)
        current = by_id.get(current.parent_id) if current.parent_id is not None else None
    names.reverse()
    return " › ".join(names)


def world_cast_of(data: WorldAssemblyInput) -> list[CastMember]:
    """Active safety cast: everyone present, arriving, speaking, or scheduled (all cast for narrator)."""
    cast_by_id = {entry.id: entry for entry in data.cast}
    if data.speaker_id == "narrator":
        active_ids = dict.fromkeys(entry.id for entry in data.cast)
    else:
        active_ids = dict.fromkeys(
            [
                *data.present_ids,
                *data.arriving_ids,
                *data.safety_cast_ids,
                *([data.speaker_id] if data.speaker_id in cast_by_id else []),
            ]
        )
    members = [safety.cast_from_card(cast_by_id[cid].card) for cid in active_ids if cid in cast_by_id]
    if data.persona is not None and data.persona.age is not None:
        members.append(CastMember(name=data.persona.name, age=data.persona.age))
    members.extend(data.npcs)
    return members


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


def _render_card(card: VietrpCard, selected: Collection[str]) -> str:
    return render_prompt(
        "_shared/card.j2",
        name=card.name,
        age=card.age,
        aliases=card.aliases,
        f=_card_view(card, selected),
    )


def _lore_text(hits: Sequence[LoreHit]) -> str:
    if not hits:
        return ""
    entries = [{"title": hit.entry.title, "content": hit.entry.content} for hit in hits]
    return render_prompt("_shared/lore.j2", entries=entries)


def _persona_text(data: WorldAssemblyInput, user_name: str) -> str:
    role = data.player_role.strip()
    if data.persona is not None:
        persona_vars = data.persona.model_dump(exclude={"format", "spec_version"})
        if role:
            existing = str(persona_vars.get("notes") or "").strip()
            persona_vars["notes"] = f"{existing}\n{role}" if existing else role
        return render_prompt("_shared/persona.j2", **persona_vars)
    if role:
        return render_prompt(
            "_shared/persona.j2",
            name=user_name,
            aliases=[],
            age=None,
            gender="",
            pronouns="",
            appearance="",
            personality="",
            background="",
            notes=role,
        )
    return ""


def _resolve_role(
    data: WorldAssemblyInput, cast_by_id: dict[str, WorldCastEntry]
) -> Literal["narrator", "single_call", "character"]:
    if data.speaker_id == NARRATOR_SPEAKER_ID:
        return "narrator"
    if data.write_mode == "single_call":
        return "single_call"
    if data.speaker_id not in cast_by_id:
        raise ValueError(f"unknown speaker_id for per_character world assembly: {data.speaker_id!r}")
    return "character"


def _card_layer_text(
    data: WorldAssemblyInput,
    mode: Literal["narrator", "single_call", "character"],
    cast_by_id: dict[str, WorldCastEntry],
    relevant_entries: Sequence[WorldCastEntry],
) -> str:
    if mode == "character":
        selected = DEFAULT_CARD_FIELDS if data.card_fields is None else set(data.card_fields)
        return _render_card(cast_by_id[data.speaker_id].card, selected)
    if mode == "narrator":
        selected = NARRATOR_CARD_FIELDS if data.card_fields is None else set(data.card_fields)
        return "\n\n".join(_render_card(entry.card, selected) for entry in relevant_entries)
    selected = DEFAULT_CARD_FIELDS if data.card_fields is None else set(data.card_fields)
    entries = list(relevant_entries)
    if data.speaker_id in cast_by_id and all(e.id != data.speaker_id for e in entries):
        entries.append(cast_by_id[data.speaker_id])
    return "\n\n".join(_render_card(entry.card, selected) for entry in entries)


def _system_layers(data: WorldAssemblyInput, user_name: str) -> list[PromptLayer]:
    cast_by_id = {entry.id: entry for entry in data.cast}
    mode = _resolve_role(data, cast_by_id)

    present_entries = [cast_by_id[cid] for cid in dict.fromkeys(data.present_ids) if cid in cast_by_id]
    present_set = {entry.id for entry in present_entries}
    arriving_entries = [
        cast_by_id[cid] for cid in dict.fromkeys(data.arriving_ids) if cid in cast_by_id and cid not in present_set
    ]
    relevant_entries = [*present_entries, *arriving_entries]

    if mode == "character":
        char_label = cast_by_id[data.speaker_id].card.name
    else:
        char_label = ", ".join(entry.card.name for entry in relevant_entries) or data.world.name

    layers = [PromptLayer("system", "system", system_text(data.preset, char=char_label, user=user_name))]
    if data.nsfw:
        layers.append(PromptLayer("nsfw", "system", nsfw_text(data.preset, char=char_label, user=user_name)))

    candidates: list[tuple[str, str]] = []
    if data.world.rules.strip():
        candidates.append(
            ("world_rules", render_prompt("_shared/world_rules.j2", world_name=data.world.name, rules=data.world.rules))
        )

    loc_by_id = {loc.id: loc for loc in data.world.locations}
    current_loc = loc_by_id.get(data.location_id)
    loc_desc = current_loc.description.strip() if current_loc is not None else ""
    visible = visible_scene(data.scene, data.present_ids) if data.scene is not None else None
    char_names = {entry.id: entry.card.name for entry in data.cast}
    candidates.append(
        (
            "location_path",
            render_prompt(
                "_shared/location_path.j2",
                path=location_path(data.world.locations, data.location_id),
                location_description=loc_desc,
                time=data.time.strip(),
                tension=max(0, min(4, data.tension)),
                scene=visible,
                char_names=char_names,
            ),
        )
    )

    candidates.append(
        (
            "present_cast",
            render_prompt(
                "_shared/present_cast.j2",
                user_name=user_name,
                present=[{"id": e.id, "name": e.card.name, "tagline": e.card.tagline} for e in present_entries],
                arriving=[{"id": e.id, "name": e.card.name, "tagline": e.card.tagline} for e in arriving_entries],
                npcs=[{"name": npc.name, "age": npc.age} for npc in data.npcs],
            ),
        )
    )

    before, after = order_by_position(data.lore)
    candidates.append(("lore_before", _lore_text(before)))
    candidates.append(("card", _card_layer_text(data, mode, cast_by_id, relevant_entries)))
    candidates.append(("lore_after", _lore_text(after)))

    persona_block = _persona_text(data, user_name)
    if persona_block:
        candidates.append(("persona", persona_block))

    if data.bonds:
        bonds = [{"pair": bond.pair, "fields": dict(bond.fields)} for bond in data.bonds]
        candidates.append(("bonds", render_prompt("_shared/bonds.j2", bonds=bonds)))

    if data.summary.strip() or data.events:
        candidates.append(
            ("memory", render_prompt("_shared/memory.j2", summary=data.summary.strip(), events=list(data.events)))
        )

    if data.command is not None and data.command.kind == "cmd" and data.command.instruction:
        instruction = substitute_placeholders(data.command.instruction, char=char_label, user=user_name)
        candidates.append(("cmd_instruction", render_prompt("_shared/cmd_instruction.j2", instruction=instruction)))

    speaker_name = cast_by_id[data.speaker_id].card.name if mode == "character" else ""
    candidates.append(
        (
            "world_role",
            render_prompt(
                "_shared/world_role.j2",
                mode=mode,
                speaker_id=data.speaker_id,
                speaker_name=speaker_name,
                user_name=user_name,
                entering=data.entering,
                co_arriving_names=[e.card.name for e in arriving_entries if e.id != data.speaker_id],
                absent_names=[e.card.name for e in data.cast if e.id not in present_set],
                present_speakers=[{"id": e.id, "name": e.card.name} for e in relevant_entries],
            ),
        )
    )

    candidates.append(
        (
            "scene_instruction",
            render_prompt(
                "_shared/scene_instruction.j2",
                mode=mode,
                speaker_id=data.speaker_id,
                present_ids=[e.id for e in relevant_entries],
            ),
        )
    )

    layers.extend(PromptLayer(name, "system", text) for name, text in candidates if text)
    return layers


def assemble_world(data: WorldAssemblyInput) -> AssembledPrompt:
    """Build the world-chat prompt. Raises `AppError("age_required")` when any cast card has no age."""
    # Check the whole world cast so an un-aged card cannot slip in even when initially absent.
    safety.assert_cast_usable([safety.cast_from_card(entry.card) for entry in data.cast])
    cast = world_cast_of(data)
    safety.assert_cast_usable(cast)

    user_name = data.persona.name if data.persona is not None else FALLBACK_USER_NAME
    system_layers = safety.apply(_system_layers(data, user_name), cast, None)

    overhead = LLMConfig().tokens_per_message
    factor = data.corrections.factor(data.model)

    def tokens_of(text: str) -> int:
        return math.ceil(count_text(text) * factor)

    def cost(text: str) -> int:
        return math.ceil((count_text(text) + overhead) * factor)

    prefill = (data.prefill or "").strip()
    fixed = sum(cost(layer.text) for layer in system_layers) + (cost(prefill) if prefill else 0)
    remaining = data.budget.prompt_budget - fixed
    kept: list[HistoryMessage] = []
    for message in reversed(data.messages):
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
        history_dropped=len(data.messages) - len(kept),
        over_budget=remaining < 0,
    )
