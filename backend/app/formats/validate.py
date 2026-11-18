"""Validation entry points for stored format data, with soft warnings."""

from __future__ import annotations

from typing import Any

from app.formats.card import VietrpCard
from app.formats.common import FormatWarning
from app.formats.lorebook import Lorebook
from app.formats.migrations import migrate
from app.formats.persona import Persona
from app.formats.world import VietrpWorld
from app.pipeline.safety import card_has_minor, is_nsfw_tagged

__all__ = ["card_has_minor", "is_nsfw_tagged"]

# Convention from the architecture (section 4.1): each entry stays under ~300 chars.
FIELD_LONG_LIMIT = 300
IMPERATIVE_PREFIXES = ("hãy", "bạn là")

_CARD_TEXT_FIELDS = ("appearance", "personality", "backstory", "goals")


def _text_warnings(path: str, text: str) -> list[FormatWarning]:
    out: list[FormatWarning] = []
    if len(text) > FIELD_LONG_LIMIT:
        out.append(
            FormatWarning(
                path=path,
                code="field_long",
                message=f"{path} is longer than {FIELD_LONG_LIMIT} characters",
            )
        )
    if text.strip().lower().startswith(IMPERATIVE_PREFIXES):
        out.append(
            FormatWarning(
                path=path,
                code="imperative_text",
                message=f"{path} reads as an instruction instead of a description",
            )
        )
    return out


def validate_card(data: dict[str, Any], *, allow_missing_age: bool) -> tuple[VietrpCard, list[FormatWarning]]:
    card = VietrpCard.model_validate(migrate("vietrp-card", data))
    warnings: list[FormatWarning] = []
    if card.age is None:
        if not allow_missing_age:
            raise ValueError("age is required")
        warnings.append(FormatWarning(path="age", code="age_missing", message="age is missing"))
    for field in _CARD_TEXT_FIELDS:
        warnings.extend(_text_warnings(field, getattr(card, field)))
    for index, secret in enumerate(card.secrets):
        warnings.extend(_text_warnings(f"secrets.{index}.content", secret.content))
    return card, warnings


def validate_world(data: dict[str, Any]) -> tuple[VietrpWorld, list[FormatWarning]]:
    world = VietrpWorld.model_validate(migrate("vietrp-world", data))
    warnings = _text_warnings("rules", world.rules)
    for loc in world.locations:
        warnings.extend(_text_warnings(f"locations.{loc.id}.description", loc.description))
    return world, warnings


def validate_persona(data: dict[str, Any]) -> tuple[Persona, list[FormatWarning]]:
    persona = Persona.model_validate(migrate("vietrp-persona", data))
    warnings: list[FormatWarning] = []
    for field in ("appearance", "personality", "background"):
        warnings.extend(_text_warnings(field, getattr(persona, field)))
    return persona, warnings


def validate_lorebook(data: dict[str, Any]) -> tuple[Lorebook, list[FormatWarning]]:
    lorebook = Lorebook.model_validate(migrate("vietrp-lorebook", data))
    warnings: list[FormatWarning] = []
    for entry in lorebook.entries:
        warnings.extend(_text_warnings(f"entries.{entry.id}.content", entry.content))
    return lorebook, warnings
