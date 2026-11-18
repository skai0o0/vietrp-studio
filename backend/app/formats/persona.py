"""Persona format (architecture section 4.3)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.formats.common import CURRENT_SPEC_VERSION, FormatModel, SpecVersion


class Persona(FormatModel):
    format: Literal["vietrp-persona"] = "vietrp-persona"
    spec_version: SpecVersion = CURRENT_SPEC_VERSION
    name: str = Field(min_length=1, max_length=80)
    aliases: list[str] = Field(default_factory=list)
    age: int | None = Field(default=None, ge=0, le=10000)
    gender: str = ""
    pronouns: str = ""
    appearance: str = ""
    personality: str = ""
    background: str = ""
    notes: str = ""
