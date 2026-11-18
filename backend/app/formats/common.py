"""Shared types for the VietRP data formats."""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

# Slug used for ids inside card/world content (AGENTS.md section 4.3).
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]{1,40}$")]

Visibility = Literal["public", "private"]

SpecVersion = Literal["1.0"]
CURRENT_SPEC_VERSION: SpecVersion = "1.0"


class FormatModel(BaseModel):
    """Base for all stored format models: unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")


class FormatWarning(BaseModel):
    """A soft issue found during validation; never blocks a write."""

    path: str
    code: str
    message: str


# Zero-width and bidi format characters that make two visually identical tags compare unequal.
_INVISIBLE_CHARS = re.compile("[\u200b-\u200f\u2060\ufeff]")
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_tag(tag: str) -> str:
    """Canonical tag form: NFKC, invisible characters removed, whitespace collapsed, stripped."""
    text = unicodedata.normalize("NFKC", tag)
    text = _INVISIBLE_CHARS.sub("", text)
    return _WHITESPACE_RUN.sub(" ", text).strip()


def normalize_tags(tags: list[str]) -> list[str]:
    """Validator body shared by card and world: normalise first, then reject empty or non-lowercase."""
    out: list[str] = []
    for tag in tags:
        value = normalize_tag(tag)
        if not value:
            raise ValueError("tags must not be empty")
        if value != value.lower():
            raise ValueError("tags must be lowercase")
        out.append(value)
    return out
