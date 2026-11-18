"""SSE turn events (AGENTS section 4.5, architecture section 8). One model per event name.

No event may carry secrets or raw provider errors. `notice.detail` is English, for logs.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from app.schemas.world_state import WorldState


class _Event(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanSpeaker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["character", "narrator"]
    sentences: int = Field(ge=0)
    order: int = Field(default=0, ge=0)
    reason: str = ""


class DirectorCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    probability: float = Field(ge=0.0, le=1.0)
    passed: bool
    hint_vi: str = ""


class DirectorVerdict(BaseModel):
    """Director result; reused by the `director` event and by stored message variants."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    criteria: list[DirectorCriterion]
    attempt: int = Field(ge=0)


class PlanEvent(_Event):
    type: Literal["plan"] = "plan"
    turn_type: str
    speakers: list[PlanSpeaker]
    lore_ids: list[str] = Field(default_factory=list)
    card_fields: list[str] = Field(default_factory=list)


class SpeakerStartEvent(_Event):
    type: Literal["speaker_start"] = "speaker_start"
    message_id: str
    speaker: str
    seq: int = Field(ge=0)


class DraftEvent(_Event):
    type: Literal["draft"] = "draft"
    delta: str


class DirectorEvent(DirectorVerdict):
    type: Literal["director"] = "director"


class ContentEvent(_Event):
    type: Literal["content"] = "content"
    delta: str


class ResetContentEvent(_Event):
    type: Literal["reset_content"] = "reset_content"
    message_id: str


class RejudgeEvent(_Event):
    type: Literal["rejudge"] = "rejudge"
    attempt: int = Field(ge=0)


class SceneEvent(_Event):
    """World chat only (P3)."""

    type: Literal["scene"] = "scene"
    delta: dict[str, Any] = Field(default_factory=dict)
    merged: dict[str, Any] = Field(default_factory=dict)


class SpeakerEndEvent(_Event):
    type: Literal["speaker_end"] = "speaker_end"
    message_id: str
    variant_idx: int = Field(ge=0)
    stopped: bool = False


class StateEvent(_Event):
    """World chat only (P3)."""

    type: Literal["state"] = "state"
    state: WorldState
    changed: list[str] = Field(default_factory=list)
    confidence: dict[str, float] = Field(default_factory=dict)


class ArchivistEvent(_Event):
    """Used from P4."""

    type: Literal["archivist"] = "archivist"
    summary: str | None = None
    events_added: int = Field(default=0, ge=0)


class BondsEvent(_Event):
    type: Literal["bonds"] = "bonds"
    bonds: dict[str, Any]


class NoticeEvent(_Event):
    type: Literal["notice"] = "notice"
    code: str
    agent: str | None = None
    detail: str | None = None


class UsageEvent(_Event):
    type: Literal["usage"] = "usage"
    agent: str
    model: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(default=0, ge=0)
    cost: float = Field(ge=0.0)


class PingEvent(_Event):
    type: Literal["ping"] = "ping"


class DoneEvent(_Event):
    type: Literal["done"] = "done"
    message_ids: list[str]


class ErrorEvent(_Event):
    type: Literal["error"] = "error"
    code: str


TurnEvent = Annotated[
    PlanEvent
    | SpeakerStartEvent
    | DraftEvent
    | DirectorEvent
    | ContentEvent
    | ResetContentEvent
    | RejudgeEvent
    | SceneEvent
    | SpeakerEndEvent
    | StateEvent
    | ArchivistEvent
    | BondsEvent
    | NoticeEvent
    | UsageEvent
    | PingEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


class TurnEventEnvelope(RootModel[TurnEvent]):
    """Wrapper used for validation and for the exported JSON Schema of the union."""


class TurnEventDoc(BaseModel):
    """Object-rooted wrapper so the exported JSON Schema (and generated TS) has an object root."""

    model_config = ConfigDict(extra="forbid")

    event: TurnEvent
