"""`vietrp-card` format (architecture section 4.1)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.formats.common import CURRENT_SPEC_VERSION, FormatModel, Slug, SpecVersion, normalize_tags

Tag = Annotated[str, Field(min_length=1, max_length=32)]


class Secret(FormatModel):
    id: Slug
    content: str
    reveal_when: str = ""


class Speech(FormatModel):
    style: str = ""
    catchphrases: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class Addressing(FormatModel):
    default: str = ""
    user: str = ""
    by_character: dict[Slug, str] = Field(default_factory=dict)


class Relationships(FormatModel):
    user: str = ""
    by_character: dict[Slug, str] = Field(default_factory=dict)


class VietrpCard(FormatModel):
    format: Literal["vietrp-card"] = "vietrp-card"
    spec_version: SpecVersion = CURRENT_SPEC_VERSION
    name: str = Field(min_length=1, max_length=80)
    # None is only accepted for imported cards (see validate_card).
    age: int | None = Field(default=None, ge=0, le=10000)
    is_fictional: Literal[True] = True
    aliases: list[str] = Field(default_factory=list)
    tagline: str = Field(default="", max_length=140)
    appearance: str = ""
    personality: str = ""
    backstory: str = ""
    goals: str = ""
    limits: list[str] = Field(default_factory=list)
    secrets: list[Secret] = Field(default_factory=list)
    speech: Speech = Field(default_factory=Speech)
    addressing: Addressing = Field(default_factory=Addressing)
    relationships: Relationships = Field(default_factory=Relationships)
    greetings: list[str] = Field(default_factory=list)
    lorebook_ids: list[UUID] = Field(default_factory=list)
    extras: dict[Slug, str] = Field(default_factory=dict)
    tags: list[Tag] = Field(default_factory=list, max_length=20)

    @field_validator("tags")
    @classmethod
    def _tags_normalized(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)
