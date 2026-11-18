"""API models for chats (single and world): chats, messages, turns, per-chat settings, state patches, prompt preview."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.events import DirectorVerdict
from app.schemas.world_state import StatePatch as StatePatch
from app.schemas.world_state import WorldState as WorldState

DirectorStreamMode = Literal["draft_then_replace", "hold_until_approved"]
LorebookMode = Literal["hybrid", "keyword", "ai"]
GroupWriteMode = Literal["per_character", "single_call"]
# "off" disables reasoning; "auto" lets the model decide; "low" | "medium" | "high" set the effort.
ReasoningEffort = Literal["off", "auto", "low", "medium", "high"]


class DirectorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    stream_mode: DirectorStreamMode = "draft_then_replace"


class LorebookSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: LorebookMode = "hybrid"
    # The chat's own lorebook list. None = the books linked to the card/world when the chat was created
    # (`ChatOut.default_lorebook_ids`); a list (even empty) replaces them for this chat only.
    book_ids: list[uuid.UUID] | None = None


class MemorySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None means "use the context length of the model" (architecture 3.1: per model).
    context_length: int | None = Field(default=None, gt=0)
    summarize_at: float = Field(default=0.8, gt=0.0, le=1.0)


class WriterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning: ReasoningEffort = "medium"


class GroupSettings(BaseModel):
    """World chat only (P3); defined now so settings stay one shape."""

    model_config = ConfigDict(extra="forbid")

    write_mode: GroupWriteMode = "per_character"
    chain_max: int = Field(default=3, ge=1)


class AgentModels(BaseModel):
    """Per-agent model id overrides. None keeps the default from `llm/defaults.py`."""

    model_config = ConfigDict(extra="forbid")

    orchestrator: str | None = None
    writer: str | None = None
    director: str | None = None
    state_keeper: str | None = None
    archivist: str | None = None
    creator: str | None = None
    card_judge: str | None = None
    bond_drafter: str | None = None
    bond_selector: str | None = None


class ChatSettings(BaseModel):
    """Per-chat overrides of the user's global settings (architecture 3.1)."""

    model_config = ConfigDict(extra="forbid")

    director: DirectorSettings = Field(default_factory=DirectorSettings)
    writer: WriterSettings = Field(default_factory=WriterSettings)
    lorebook: LorebookSettings = Field(default_factory=LorebookSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    group: GroupSettings = Field(default_factory=GroupSettings)
    nsfw: bool = False
    models: AgentModels = Field(default_factory=AgentModels)


class CastMemberSummary(BaseModel):
    """Summary of one cast member in a world chat."""

    id: str
    character_id: str
    name: str
    tagline: str = ""
    avatar_url: str | None = None


class ChatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["single", "world"] = "single"
    character_id: str | None = None
    greeting_index: int = Field(default=0, ge=0)
    world_id: str | None = None
    opening_id: str | None = None
    cast_ids: list[str] = Field(default_factory=list)
    persona_id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    settings: ChatSettings | None = None

    @model_validator(mode="after")
    def _require_character_for_single(self) -> ChatCreate:
        if self.mode == "single" and not self.character_id:
            raise ValueError("character_id is required when mode is 'single'")
        return self


class ChatUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)
    persona_id: str | None = None
    settings: ChatSettings | None = None


class ChatSummary(BaseModel):
    id: str
    mode: Literal["single", "world"]
    title: str
    character_id: str = ""
    character_name: str = ""
    world_id: str | None = None
    world_name: str | None = None
    opening_id: str | None = None
    cast: list[CastMemberSummary] = Field(default_factory=list)
    persona_id: str | None
    avatar_url: str | None = None
    parent_chat_id: str | None = None
    forked_at_seq: int | None = None
    messages_count: int
    created_at: dt.datetime
    updated_at: dt.datetime


class ChatOut(ChatSummary):
    state: dict[str, Any]
    settings: ChatSettings
    # Lorebooks linked to the card/world snapshot of this chat; used while `settings.lorebook.book_ids` is None.
    default_lorebook_ids: list[str] = Field(default_factory=list)


class MessageVariantOut(BaseModel):
    idx: int = Field(ge=0)
    content: str
    stopped: bool = False
    director: DirectorVerdict | None = None
    created_at: dt.datetime
    # Only filled when the client asks with `?include=drafts`.
    draft: str | None = None


class MessageOut(BaseModel):
    id: str
    seq: int = Field(ge=0)
    speaker: str
    active_variant: int = Field(ge=0)
    variants: list[MessageVariantOut]
    meta: dict[str, Any]
    created_at: dt.datetime


class StateBondsPatch(BaseModel):
    """Body of PATCH /chats/{id}/state: hand edit of `state.bonds` (the only state in single chat)."""

    model_config = ConfigDict(extra="forbid")

    bonds: dict[str, Any]


class TurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    prefill: str | None = None


class ContinueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prefill: str | None = None


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prefill: str | None = None


class MessageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)


class ActiveVariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variant_idx: int = Field(ge=0)


class ForkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str | None = None
    upto_seq: int | None = Field(default=None, ge=0)
    title: str | None = Field(default=None, max_length=200)


class UndoResult(BaseModel):
    removed_count: int = Field(ge=0)
    chat: ChatOut


class PromptLayer(BaseModel):
    name: str
    tokens: int = Field(ge=0)
    text: str


class PromptPreview(BaseModel):
    layers: list[PromptLayer]
    total_tokens: int = Field(ge=0)
    budget: int = Field(ge=0)
