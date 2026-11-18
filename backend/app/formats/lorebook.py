"""Lorebook format (architecture section 4.4)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.formats.common import CURRENT_SPEC_VERSION, FormatModel, Slug, SpecVersion


class LorebookEntry(FormatModel):
    id: Slug
    title: str = ""
    keys: list[str] = Field(default_factory=list)
    secondary_keys: list[str] = Field(default_factory=list)
    selective: bool = False
    constant: bool = False
    priority: int = 0
    position: Literal["before_char", "after_char"] = "before_char"
    select_mode: Literal["keyword", "ai", "both"] = "keyword"
    content: str = ""
    enabled: bool = True


class Lorebook(FormatModel):
    format: Literal["vietrp-lorebook"] = "vietrp-lorebook"
    spec_version: SpecVersion = CURRENT_SPEC_VERSION
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    # Defaults as specified in WP-G (scan depth in messages, budget in tokens).
    scan_depth: int = Field(default=50, ge=1)
    token_budget: int = Field(default=500, ge=0)
    entries: list[LorebookEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_entry_ids(self) -> Lorebook:
        ids = [entry.id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate lorebook entry id")
        return self
