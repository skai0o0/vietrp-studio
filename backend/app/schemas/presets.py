"""Per-agent prompt presets: layers that override the default templates."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AgentId = Literal[
    "orchestrator",
    "writer",
    "director",
    "state_keeper",
    "archivist",
    "creator",
    "card_judge",
    "bond_drafter",
    "bond_selector",
]


class PresetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent: AgentId
    name: str = Field(min_length=1, max_length=120)
    layers: dict[str, str] = Field(default_factory=dict)


class PresetOut(PresetIn):
    id: str
    created_at: dt.datetime
    updated_at: dt.datetime
