"""World-chat state, `<scene>` delta, and Live State Editor patch schemas (architecture §4.5, §4.6)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CharacterSceneState(BaseModel):
    """Per-character free-form scene fields managed via `<scene>` blocks or manual edits."""

    model_config = ConfigDict(extra="forbid")

    mood: str = ""
    outfit: str = ""
    pose: str = ""
    holding: str = ""
    condition: str = ""


class SceneState(BaseModel):
    """Merged free-form scene state stored inside `WorldState.scene`."""

    model_config = ConfigDict(extra="forbid")

    env: dict[str, str] = Field(default_factory=dict)
    chars: dict[str, CharacterSceneState] = Field(default_factory=dict)
    items: list[str] = Field(default_factory=list)


class SceneDelta(BaseModel):
    """Incremental `<scene>` update emitted by the Writer and stored in message meta."""

    model_config = ConfigDict(extra="forbid")

    env: dict[str, str] = Field(default_factory=dict)
    chars: dict[str, CharacterSceneState] = Field(default_factory=dict)
    items: list[str] | None = None


class WorldState(BaseModel):
    """Canonical `chat.state` shape for world chats (architecture §4.5)."""

    model_config = ConfigDict(extra="forbid")

    location_id: str = ""
    time: str = ""
    tension: int = Field(default=0, ge=0, le=4)
    present_ids: list[str] = Field(default_factory=list)
    awaiting_reply: list[str] = Field(default_factory=list)
    silence: dict[str, int] = Field(default_factory=dict)
    scene: SceneState = Field(default_factory=SceneState)
    bonds: dict[str, Any] = Field(default_factory=dict)
    npcs: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""
    summary_upto: int = Field(default=0, ge=0)
    events: list[dict[str, Any]] = Field(default_factory=list)
    manual: list[str] = Field(default_factory=list)


class StatePatch(BaseModel):
    """Partial update body for `PATCH /chats/{id}/state` from the Live State Editor."""

    model_config = ConfigDict(extra="forbid")

    location_id: str | None = None
    time: str | None = None
    tension: int | None = Field(default=None, ge=0, le=4)
    present_ids: list[str] | None = None
    awaiting_reply: list[str] | None = None
    silence: dict[str, int] | None = None
    scene: SceneState | None = None
    bonds: dict[str, Any] | None = None
    npcs: list[dict[str, Any]] | None = None
    summary: str | None = None
    events: list[dict[str, Any]] | None = None
