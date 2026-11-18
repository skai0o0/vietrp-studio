"""Unit tests for WP-C3 world-chat contracts (WorldState, StatePatch, events, ChatSummary/ChatCreate)."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from app.schemas import chat as chat_mod
from app.schemas import events as ev
from app.schemas import world_state as ws


def test_world_state_defaults_and_round_trip() -> None:
    empty = ws.WorldState()
    assert empty.location_id == ""
    assert empty.time == ""
    assert empty.tension == 0
    assert empty.present_ids == []
    assert empty.awaiting_reply == []
    assert empty.silence == {}
    assert empty.scene == ws.SceneState()
    assert empty.bonds == {}
    assert empty.npcs == []
    assert empty.summary == ""
    assert empty.summary_upto == 0
    assert empty.events == []
    assert empty.manual == []

    populated = ws.WorldState(
        location_id="can_tin",
        time="07:45",
        tension=3,
        present_ids=["vy", "han"],
        awaiting_reply=["vy"],
        silence={"han": 2},
        scene=ws.SceneState(
            env={"weather": "mưa nhỏ"},
            chars={
                "vy": ws.CharacterSceneState(
                    mood="vui",
                    outfit="áo sơ mi",
                    pose="ngồi tựa lưng",
                    holding="ly trà sữa",
                    condition="bình thường",
                )
            },
            items=["cuốn sổ"],
        ),
        bonds={"vy:han": {"closeness": 2}},
        npcs=[{"id": "co_ban_hang", "name": "Cô bán hàng"}],
        summary="Hai bạn gặp nhau ở căn tin.",
        summary_upto=12,
        events=[{"seq": 5, "text": "Trời đổ mưa."}],
        manual=["tension"],
    )
    again = ws.WorldState.model_validate_json(populated.model_dump_json())
    assert again == populated


def test_world_state_rejects_invalid_bounds_and_extra_keys() -> None:
    with pytest.raises(ValidationError):
        ws.WorldState.model_validate({"tension": -1})
    with pytest.raises(ValidationError):
        ws.WorldState.model_validate({"tension": 5})
    with pytest.raises(ValidationError):
        ws.WorldState.model_validate({"summary_upto": -1})
    with pytest.raises(ValidationError):
        ws.WorldState.model_validate({"bogus": 1})
    with pytest.raises(ValidationError):
        ws.CharacterSceneState.model_validate({"mood": "vui", "extra": 1})
    with pytest.raises(ValidationError):
        ws.SceneState.model_validate({"env": {}, "unknown": True})


def test_scene_delta_allows_partial_character_updates_and_none_items() -> None:
    delta = ws.SceneDelta.model_validate({"chars": {"vy": {"mood": "dỗi"}}})
    assert delta.items is None
    assert delta.env == {}
    assert delta.chars["vy"] == ws.CharacterSceneState(mood="dỗi")

    cleared_items = ws.SceneDelta.model_validate({"items": []})
    assert cleared_items.items == []

    with pytest.raises(ValidationError):
        ws.SceneDelta.model_validate({"unknown": 1})


def test_state_patch_allows_empty_and_partial_updates() -> None:
    empty = ws.StatePatch()
    assert all(value is None for value in empty.model_dump().values())

    patch = ws.StatePatch.model_validate(
        {
            "location_id": "san_thuong",
            "tension": 4,
            "scene": {"env": {"wind": "mạnh"}, "chars": {"vy": {"pose": "đứng"}}, "items": []},
        }
    )
    assert patch.location_id == "san_thuong"
    assert patch.tension == 4
    assert patch.time is None
    assert patch.scene is not None and patch.scene.chars["vy"].pose == "đứng"

    with pytest.raises(ValidationError):
        ws.StatePatch.model_validate({"tension": 5})
    with pytest.raises(ValidationError):
        ws.StatePatch.model_validate({"manual": ["time"]})


def test_world_events_contracts() -> None:
    speaker_default = ev.PlanSpeaker(id="vy", kind="character", sentences=2)
    assert speaker_default.order == 0
    assert speaker_default.reason == ""

    speaker_ordered = ev.PlanSpeaker(id="han", kind="character", sentences=3, order=1, reason="owed reply")
    assert speaker_ordered.order == 1 and speaker_ordered.reason == "owed reply"

    with pytest.raises(ValidationError):
        ev.PlanSpeaker(id="vy", kind="character", sentences=2, order=-1)

    scene_ev = ev.SceneEvent()
    assert scene_ev.delta == {} and scene_ev.merged == {}
    with pytest.raises(ValidationError):
        ev.TurnEventEnvelope.model_validate({"type": "scene", "scene": {"env": {}}})

    state_ev = ev.StateEvent(state=ws.WorldState(tension=2))
    assert state_ev.changed == [] and state_ev.confidence == {}
    with pytest.raises(ValidationError):
        ev.TurnEventEnvelope.model_validate({"type": "state", "state": {"tension": 9}})


def test_chat_contracts_and_reexports() -> None:
    assert chat_mod.WorldState is ws.WorldState
    assert chat_mod.StatePatch is ws.StatePatch
    assert hasattr(chat_mod, "StateBondsPatch")

    member = chat_mod.CastMemberSummary(id="vy", character_id="uuid-1", name="Vy")
    assert member.tagline == "" and member.avatar_url is None

    now = dt.datetime.now(dt.UTC)
    summary = chat_mod.ChatSummary(
        id="chat-1",
        mode="world",
        title="Sài Gòn mưa",
        world_id="world-1",
        world_name="Sài Gòn",
        opening_id="open-1",
        cast=[member],
        persona_id=None,
        messages_count=1,
        created_at=now,
        updated_at=now,
    )
    assert summary.character_id == "" and summary.character_name == ""
    assert summary.cast[0].id == "vy"

    chat_out = chat_mod.ChatOut(
        **summary.model_dump(), state=ws.WorldState().model_dump(), settings=chat_mod.ChatSettings()
    )
    assert chat_out.mode == "world" and chat_out.world_id == "world-1"

    world_create = chat_mod.ChatCreate.model_validate(
        {
            "mode": "world",
            "world_id": "world-1",
            "opening_id": "open-1",
            "cast_ids": ["c1", "c2"],
            "persona_id": "p1",
            "title": "Thực tại mới",
        }
    )
    assert world_create.cast_ids == ["c1", "c2"]
    assert world_create.character_id is None
