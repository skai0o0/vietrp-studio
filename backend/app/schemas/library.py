"""API request and response models for the library, gallery, assets and import/export routes."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.formats.common import FormatWarning, Visibility

TargetType = Literal["character", "world"]


class ItemWrite(BaseModel):
    """Body of POST/PUT for characters, worlds and lorebooks. `data` is validated by the service."""

    data: dict[str, Any]
    visibility: Visibility = "private"


class PersonaWrite(BaseModel):
    data: dict[str, Any]


class _SummaryBase(BaseModel):
    id: str
    name: str
    tagline: str
    tags: list[str]
    visibility: Visibility
    # Worlds have no age, so they always send false (the field keeps both summaries shape-compatible).
    needs_age: bool
    updated_at: dt.datetime


class _OutBase(BaseModel):
    data: dict[str, Any]
    is_owner: bool
    author: str
    created_at: dt.datetime
    warnings: list[FormatWarning] = Field(default_factory=list)
    judge_score: dict[str, Any] | None = None


class CharacterSummary(_SummaryBase):
    avatar_url: str | None


class CharacterOut(CharacterSummary, _OutBase):
    pass


class WorldSummary(_SummaryBase):
    cover_url: str | None


class WorldOut(WorldSummary, _OutBase):
    pass


class PersonaOut(BaseModel):
    id: str
    data: dict[str, Any]
    avatar_url: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class LorebookSummary(BaseModel):
    id: str
    name: str
    entry_count: int
    visibility: Visibility
    updated_at: dt.datetime


class LorebookOut(LorebookSummary):
    data: dict[str, Any]
    is_owner: bool
    author: str


class GalleryItem(BaseModel):
    type: TargetType
    id: str
    name: str
    tagline: str
    tags: list[str]
    image_url: str | None
    author: str
    is_owner: bool
    is_favorite: bool
    favorite_count: int
    updated_at: dt.datetime


class CharacterPage(BaseModel):
    items: list[CharacterSummary]
    next_cursor: str | None


class WorldPage(BaseModel):
    items: list[WorldSummary]
    next_cursor: str | None


class LorebookPage(BaseModel):
    items: list[LorebookSummary]
    next_cursor: str | None


class GalleryPage(BaseModel):
    items: list[GalleryItem]
    next_cursor: str | None


class FavoritesResponse(BaseModel):
    items: list[GalleryItem]


class CharacterResponse(BaseModel):
    character: CharacterOut


class WorldResponse(BaseModel):
    world: WorldOut


class PersonaResponse(BaseModel):
    persona: PersonaOut


class PersonaListResponse(BaseModel):
    items: list[PersonaOut]


class LorebookResponse(BaseModel):
    lorebook: LorebookOut


class ImportResponse(BaseModel):
    kind: Literal["character", "world", "lorebook"]
    character: CharacterOut | None = None
    world: WorldOut | None = None
    lorebook: LorebookOut | None = None
    warnings: list[FormatWarning]
    needs_age: bool
