"""API request, response, and SSE event schemas for Creator and Card Judge."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.formats.common import FormatWarning, Visibility
from app.schemas.events import NoticeEvent, PingEvent, UsageEvent
from app.schemas.library import CharacterOut, TargetType, WorldOut

CreatorMode = Literal["slots", "chat"]


class CardJudgeCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    probability: float = Field(ge=0.0, le=1.0)
    passed: bool
    hint_vi: str = ""


class CardJudgeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)
    criteria: list[CardJudgeCriterion]


class CreatorPoolsOut(BaseModel):
    character: dict[str, dict[str, list[str]]]
    world: dict[str, dict[str, list[str]]]


class CreatorMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CreatorSessionCreate(BaseModel):
    mode: CreatorMode
    target_type: TargetType
    seed: dict[str, Any] = Field(default_factory=dict)


class CreatorSessionUpdate(BaseModel):
    seed: dict[str, Any] | None = None
    raw: str | None = None


class CreatorSessionOut(BaseModel):
    id: str
    mode: CreatorMode
    target_type: TargetType
    seed: dict[str, Any]
    messages: list[CreatorMessage]
    raw: str | None = None
    result: dict[str, Any] | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


class CreatorMessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class CreatorGenerateIn(BaseModel):
    skip_raw: bool = False
    raw: str | None = None
    seed: dict[str, Any] | None = None


class CreatorSaveIn(BaseModel):
    visibility: Visibility = "private"
    data: dict[str, Any] | None = None


class CreatorSaveOut(BaseModel):
    target_type: TargetType
    item_id: str
    character: CharacterOut | None = None
    world: WorldOut | None = None


class _CreatorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreatorDeltaEvent(_CreatorEvent):
    type: Literal["delta"] = "delta"
    delta: str


class CreatorMessageEvent(_CreatorEvent):
    type: Literal["message"] = "message"
    message: CreatorMessage


class CreatorRawEvent(_CreatorEvent):
    type: Literal["raw"] = "raw"
    raw: str


class CreatorFormattedEvent(_CreatorEvent):
    type: Literal["formatted"] = "formatted"
    data: dict[str, Any]


class CreatorValidatedEvent(_CreatorEvent):
    type: Literal["validated"] = "validated"
    data: dict[str, Any]
    warnings: list[FormatWarning] = Field(default_factory=list)


class CreatorJudgedEvent(_CreatorEvent):
    type: Literal["judged"] = "judged"
    judge_score: CardJudgeResult


class CreatorDoneEvent(_CreatorEvent):
    type: Literal["done"] = "done"
    session: CreatorSessionOut


class CreatorErrorEvent(_CreatorEvent):
    type: Literal["error"] = "error"
    code: str


CreatorEvent = Annotated[
    CreatorDeltaEvent
    | CreatorMessageEvent
    | CreatorRawEvent
    | CreatorFormattedEvent
    | CreatorValidatedEvent
    | CreatorJudgedEvent
    | NoticeEvent
    | UsageEvent
    | PingEvent
    | CreatorDoneEvent
    | CreatorErrorEvent,
    Field(discriminator="type"),
]


class CreatorEventDoc(BaseModel):
    """Object-rooted wrapper so the exported JSON Schema has an object root."""

    model_config = ConfigDict(extra="forbid")

    event: CreatorEvent
