"""`vietrp-world` format (architecture section 4.2)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.formats.card import Tag
from app.formats.common import CURRENT_SPEC_VERSION, FormatModel, Slug, SpecVersion, normalize_tags

LocationLevel = Literal["galaxy", "star_system", "planet", "country", "province", "district", "area", "place"]
# Ordered from the highest to the lowest level.
LEVEL_ORDER: tuple[str, ...] = (
    "galaxy",
    "star_system",
    "planet",
    "country",
    "province",
    "district",
    "area",
    "place",
)
_LEVEL_RANK = {level: rank for rank, level in enumerate(LEVEL_ORDER)}


class Location(FormatModel):
    id: Slug
    parent_id: Slug | None = None
    level: LocationLevel
    name: str = Field(min_length=1)
    description: str = ""


class Opening(FormatModel):
    id: Slug
    title: str = ""
    message: str = ""
    time: str = ""
    location_id: Slug
    present_ids: list[Slug] = Field(default_factory=list)
    tension: Annotated[int, Field(ge=0, le=4)] = 0
    player_role: str = ""


class VietrpWorld(FormatModel):
    format: Literal["vietrp-world"] = "vietrp-world"
    spec_version: SpecVersion = CURRENT_SPEC_VERSION
    name: str = Field(min_length=1, max_length=80)
    rules: str = ""
    tags: list[Tag] = Field(default_factory=list, max_length=20)
    lorebook_ids: list[UUID] = Field(default_factory=list)
    locations: list[Location] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _tags_normalized(cls, value: list[str]) -> list[str]:
        return normalize_tags(value)

    @model_validator(mode="after")
    def _check_location_tree(self) -> VietrpWorld:
        by_id: dict[str, Location] = {}
        for loc in self.locations:
            if loc.id in by_id:
                raise ValueError(f"duplicate location id: {loc.id}")
            by_id[loc.id] = loc
        for loc in self.locations:
            if loc.parent_id is None:
                continue
            parent = by_id.get(loc.parent_id)
            if parent is None:
                raise ValueError(f"location {loc.id}: parent {loc.parent_id} does not exist")
            if _LEVEL_RANK[loc.level] <= _LEVEL_RANK[parent.level]:
                raise ValueError(
                    f"location {loc.id}: level {loc.level} must be deeper than parent level {parent.level}"
                )
        # Strictly deeper levels already make cycles impossible; this check is a
        # defensive second line and keeps the error message explicit.
        for loc in self.locations:
            seen: set[str] = set()
            current: Location | None = loc
            while current is not None and current.parent_id is not None:
                if current.id in seen:
                    raise ValueError(f"location cycle detected at {current.id}")
                seen.add(current.id)
                current = by_id.get(current.parent_id)
        opening_ids: set[str] = set()
        for opening in self.openings:
            if opening.id in opening_ids:
                raise ValueError(f"duplicate opening id: {opening.id}")
            opening_ids.add(opening.id)
            if opening.location_id not in by_id:
                raise ValueError(f"opening {opening.id}: location {opening.location_id} does not exist")
        return self
