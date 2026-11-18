from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import BaseModel, ValidationError

from app.formats.export_schema import SCHEMAS, export_schemas
from app.schemas import chat as chat_mod
from app.schemas import events as ev
from app.schemas import presets as presets_mod
from app.schemas import world_state as world_state_mod
from app.schemas.chat import ChatSettings

EVENT_NAMES = {
    "plan",
    "speaker_start",
    "draft",
    "director",
    "content",
    "reset_content",
    "rejudge",
    "scene",
    "speaker_end",
    "state",
    "archivist",
    "bonds",
    "notice",
    "usage",
    "ping",
    "done",
    "error",
}

SAMPLES: list[dict[str, Any]] = [
    {
        "type": "plan",
        "turn_type": "dialogue",
        "speakers": [
            {"id": "vy", "kind": "character", "sentences": 3, "order": 0, "reason": "addressed"},
            {"id": "han", "kind": "character", "sentences": 2, "order": 1, "reason": "reacts"},
        ],
        "lore_ids": ["l1"],
        "card_fields": ["appearance"],
    },
    {"type": "speaker_start", "message_id": "m1", "speaker": "vy", "seq": 2},
    {"type": "draft", "delta": "xin"},
    {
        "type": "director",
        "passed": False,
        "score": 0.4,
        "criteria": [{"id": "answers_last", "probability": 0.4, "passed": False, "hint_vi": "Trả lời đúng ý"}],
        "attempt": 1,
    },
    {"type": "content", "delta": "chào"},
    {"type": "reset_content", "message_id": "m1"},
    {"type": "rejudge", "attempt": 2},
    {
        "type": "scene",
        "delta": {"env": {"weather": "mưa"}},
        "merged": {"env": {"weather": "mưa"}, "chars": {}, "items": []},
    },
    {"type": "speaker_end", "message_id": "m1", "variant_idx": 0, "stopped": True},
    {
        "type": "state",
        "state": {"location_id": "pho_di_bo", "time": "20:00", "tension": 1, "present_ids": ["vy"]},
        "changed": ["location_id", "time", "tension", "present_ids"],
        "confidence": {"location_id": 0.9, "tension": 0.8},
    },
    {"type": "archivist", "summary": "s", "events_added": 1},
    {"type": "bonds", "bonds": {"vy": {"closeness": 2}}},
    {"type": "notice", "code": "agent_failed", "agent": "bond_selector", "detail": "timeout"},
    {
        "type": "usage",
        "agent": "writer",
        "model": "m",
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "reasoning_tokens": 0,
        "cost": 0.001,
    },
    {"type": "ping"},
    {"type": "done", "message_ids": ["m1"]},
    {"type": "error", "code": "turn_failed"},
]


def test_samples_cover_every_event_name() -> None:
    assert {s["type"] for s in SAMPLES} == EVENT_NAMES
    members = get_args(get_args(ev.TurnEvent)[0])
    assert len(members) == len(EVENT_NAMES)


@pytest.mark.parametrize("sample", SAMPLES, ids=[s["type"] for s in SAMPLES])
def test_event_round_trips_through_json(sample: dict[str, Any]) -> None:
    event = ev.TurnEventEnvelope.model_validate(sample).root
    assert event.type == sample["type"]
    text = event.model_dump_json()
    again = ev.TurnEventEnvelope.model_validate_json(text).root
    assert again == event
    assert json.loads(text)["type"] == sample["type"]


def test_union_discriminates_to_the_right_class() -> None:
    assert isinstance(ev.TurnEventEnvelope.model_validate({"type": "ping"}).root, ev.PingEvent)
    assert isinstance(ev.TurnEventEnvelope.model_validate({"type": "content", "delta": "x"}).root, ev.ContentEvent)
    with pytest.raises(ValidationError):
        ev.TurnEventEnvelope.model_validate({"type": "nope"})
    with pytest.raises(ValidationError):
        ev.TurnEventEnvelope.model_validate({"type": "content", "delta": "x", "extra": 1})


def _field_names(model: type[BaseModel], seen: set[type[BaseModel]]) -> set[str]:
    if model in seen:
        return set()
    seen.add(model)
    names = set(model.model_fields)
    for name, info in model.model_fields.items():
        del name
        stack = [info.annotation]
        while stack:
            ann = stack.pop()
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                names |= _field_names(ann, seen)
            else:
                stack.extend(get_args(ann))
    return names


def test_no_field_name_suggests_a_secret() -> None:
    forbidden = ("api_key", "apikey", "secret", "passphrase", "password", "kek", "dek", "authorization", "bearer")
    all_models: list[type[BaseModel]] = []
    for mod in (ev, chat_mod, presets_mod, world_state_mod):
        for obj in vars(mod).values():
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj.__module__ == mod.__name__:
                all_models.append(obj)
    seen: set[type[BaseModel]] = set()
    names: set[str] = set()
    for model in all_models:
        names |= _field_names(model, seen)
    bad = {n for n in names if any(f == n.lower() or f in n.lower() for f in forbidden)}
    assert not bad


def test_settings_defaults_match_architecture() -> None:
    s = ChatSettings()
    assert s.director.enabled is True
    assert s.director.stream_mode == "draft_then_replace"
    assert s.group.write_mode == "per_character"
    assert s.lorebook.mode == "hybrid"
    assert s.memory.summarize_at == 0.8
    assert s.memory.context_length is None
    assert s.group.chain_max == 3
    assert s.nsfw is False
    assert all(v is None for v in s.models.model_dump().values())


def test_settings_forbid_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        ChatSettings.model_validate({"director": {"enabled": True, "bogus": 1}})
    with pytest.raises(ValidationError):
        ChatSettings.model_validate({"bogus": 1})
    with pytest.raises(ValidationError):
        ChatSettings.model_validate({"director": {"stream_mode": "other"}})


def test_chat_create_mode_values() -> None:
    chat_mod.ChatCreate.model_validate({"character_id": "c"})
    # "world" parses; the service rejects it with `mode_unsupported` until WP-V lands.
    chat_mod.ChatCreate.model_validate({"mode": "world", "character_id": "c"})
    world_body = chat_mod.ChatCreate.model_validate(
        {"mode": "world", "world_id": "w1", "opening_id": "o1", "cast_ids": ["c1", "c2"]}
    )
    assert world_body.mode == "world" and world_body.cast_ids == ["c1", "c2"]
    with pytest.raises(ValidationError):
        chat_mod.ChatCreate.model_validate({"mode": "single"})
    with pytest.raises(ValidationError):
        chat_mod.ChatCreate.model_validate({"mode": "x", "character_id": "c"})


def test_preset_agent_is_restricted() -> None:
    presets_mod.PresetIn.model_validate({"agent": "writer", "name": "n", "layers": {"system": "x"}})
    with pytest.raises(ValidationError):
        presets_mod.PresetIn.model_validate({"agent": "evil", "name": "n"})


def test_schema_export_is_deterministic_and_complete(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    export_schemas(a)
    export_schemas(b)
    names = sorted(p.name for p in a.iterdir())
    assert names == sorted(SCHEMAS)
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes()
    events_schema = json.loads((a / "events.schema.json").read_text(encoding="utf-8"))
    assert "discriminator" in json.dumps(events_schema)
