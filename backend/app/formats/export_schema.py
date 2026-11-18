"""Export JSON Schemas for the frontend: `python -m app.formats.export_schema <out_dir>`."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from app.formats.card import VietrpCard
from app.formats.lorebook import Lorebook
from app.formats.persona import Persona
from app.formats.world import VietrpWorld
from app.schemas.chat import (
    ActiveVariantRequest,
    ChatCreate,
    ChatOut,
    ChatSettings,
    ChatSummary,
    ChatUpdate,
    ContinueRequest,
    ForkRequest,
    MessageOut,
    MessageUpdate,
    PromptPreview,
    RegenerateRequest,
    TurnRequest,
    UndoResult,
)
from app.schemas.creator import (
    CardJudgeResult,
    CreatorEventDoc,
    CreatorGenerateIn,
    CreatorMessageIn,
    CreatorPoolsOut,
    CreatorSaveIn,
    CreatorSaveOut,
    CreatorSessionCreate,
    CreatorSessionOut,
    CreatorSessionUpdate,
)
from app.schemas.events import TurnEventDoc
from app.schemas.presets import PresetIn, PresetOut
from app.schemas.world_state import StatePatch, WorldState

SCHEMAS: dict[str, type[BaseModel]] = {
    "vietrp-card.schema.json": VietrpCard,
    "vietrp-world.schema.json": VietrpWorld,
    "persona.schema.json": Persona,
    "lorebook.schema.json": Lorebook,
    "card-judge-result.schema.json": CardJudgeResult,
    "creator-events.schema.json": CreatorEventDoc,
    "creator-generate-in.schema.json": CreatorGenerateIn,
    "creator-message-in.schema.json": CreatorMessageIn,
    "creator-pools-out.schema.json": CreatorPoolsOut,
    "creator-save-in.schema.json": CreatorSaveIn,
    "creator-save-out.schema.json": CreatorSaveOut,
    "creator-session-create.schema.json": CreatorSessionCreate,
    "creator-session-out.schema.json": CreatorSessionOut,
    "creator-session-update.schema.json": CreatorSessionUpdate,
    "chat-create.schema.json": ChatCreate,
    "chat-update.schema.json": ChatUpdate,
    "chat-summary.schema.json": ChatSummary,
    "chat-out.schema.json": ChatOut,
    "chat-settings.schema.json": ChatSettings,
    "chat-message.schema.json": MessageOut,
    "chat-turn-request.schema.json": TurnRequest,
    "chat-continue-request.schema.json": ContinueRequest,
    "chat-regenerate-request.schema.json": RegenerateRequest,
    "chat-message-update.schema.json": MessageUpdate,
    "chat-active-variant-request.schema.json": ActiveVariantRequest,
    "chat-fork-request.schema.json": ForkRequest,
    "chat-undo-result.schema.json": UndoResult,
    "chat-prompt-preview.schema.json": PromptPreview,
    "events.schema.json": TurnEventDoc,
    "presets-in.schema.json": PresetIn,
    "presets-out.schema.json": PresetOut,
    "world-state.schema.json": WorldState,
    "state-patch.schema.json": StatePatch,
}


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in SCHEMAS.items():
        text = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        path = out_dir / filename
        path.write_bytes(text.encode("utf-8"))
        written.append(path)
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m app.formats.export_schema <out_dir>", file=sys.stderr)
        return 2
    export_schemas(Path(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
