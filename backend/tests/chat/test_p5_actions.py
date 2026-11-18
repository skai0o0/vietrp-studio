"""P5 end-to-end tests: state commands, anti-repeat, continue, regenerate/swipe, edit, delete, undo, fork."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from app.core.deps import get_gateway_factory
from app.services.chat_service import get_unit_of_work, parse_chat_id
from app.services.turn_service import ensure_openrouter_key, get_key_check
from tests.chat.conftest import (
    COMPLETIONS,
    ChatEnv,
    decision,
    make_character,
    make_chat,
    make_persona,
    parse_sse,
    run_turn,
    script_llm,
    sse_stream,
)
from tests.chat.test_memory import _archivist_response
from tests.chat.test_world_chat import make_world, make_world_chat
from tests.chat.test_world_turn import _script_world_llm

RULE_MARKER = "QUY TẮC AN TOÀN BẮT BUỘC"


def _types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


async def _messages(client: httpx.AsyncClient, chat_id: str, suffix: str = "") -> list[dict[str, Any]]:
    resp = await client.get(f"/api/chats/{chat_id}/messages{suffix}")
    assert resp.status_code == 200, resp.text
    result: list[dict[str, Any]] = resp.json()
    return result


def _is_writer_req(request: httpx.Request) -> bool:
    return request.url.path == COMPLETIONS and b'"stream":true' in request.content.replace(b" ", b"")


async def _setup_world_chat(env: ChatEnv, *, write_mode: str = "per_character") -> dict[str, Any]:
    vy_id = await make_character(env.a, name="Trần Hạ Vy", age=20, tagline="Lớp phó")
    han_id = await make_character(env.a, name="Nguyễn Gia Hân", age=21, tagline="Thư viện trưởng")
    world_id = await make_world(env.a)
    persona_id = await make_persona(env.a, name="Nam")
    return await make_world_chat(
        env.a,
        world_id,
        "gio_ra_choi",
        [vy_id, han_id],
        persona_id=persona_id,
        settings={"group": {"write_mode": write_mode}},
    )


async def test_state_commands_via_turn_single_and_world(env: ChatEnv) -> None:
    # Single chat: /time & /move unsupported; /addnpc enforces minor safety for <18 and unknown-age NPCs.
    char_id = await make_character(env.a, name="Mai", age=24)
    single = await make_chat(env.a, char_id, settings={"nsfw": True})
    script_llm(env.llm, char_id, writer=[sse_stream("Mai mỉm cười chào bạn.")])

    t_single = await run_turn(env.a, single["id"], "/time 15:00")
    assert _types(t_single) == ["notice", "done"] and t_single[0]["code"] == "command_unsupported"
    m_single = await run_turn(env.a, single["id"], "/move san_thuong")
    assert _types(m_single) == ["notice", "done"] and m_single[0]["code"] == "command_unsupported"

    added = await run_turn(env.a, single["id"], "/addnpc Bé Na (13) - em họ")
    assert _types(added) == ["notice", "done"] and added[0]["code"] == "npc_added"
    added_unknown = await run_turn(env.a, single["id"], "/addnpc Người lạ - mặc áo mưa")
    assert added_unknown[0]["code"] == "npc_added"
    listed = await run_turn(env.a, single["id"], "/listnpc")
    assert listed[0]["code"] == "npc_listed"
    assert "Bé Na (13) - em họ" in listed[0]["detail"] and "Người lạ" in listed[0]["detail"]

    preview = (await env.a.get(f"/api/chats/{single['id']}/prompt-preview", params={"text": "Chào"})).json()
    system_layers = [la for la in preview["layers"] if la["name"] not in ("history", "prefill")]
    assert system_layers[-1]["name"] == "minor_rule"
    assert "Bé Na" in system_layers[-1]["text"] and "Người lạ" in system_layers[-1]["text"]

    # Also verified during an actual single-chat turn!
    await run_turn(env.a, single["id"], "Chào cả nhà")
    writer_req = next(r for r in reversed(env.llm.requests) if _is_writer_req(r))
    writer_msgs = json.loads(writer_req.content)["messages"]
    sys_msgs = [m for m in writer_msgs if m["role"] == "system"]
    assert RULE_MARKER in sys_msgs[-1]["content"] and "Bé Na" in sys_msgs[-1]["content"]

    assert (await run_turn(env.a, single["id"], "/removenpc Bé Na"))[0]["code"] == "npc_removed"
    assert (await run_turn(env.a, single["id"], "/removenpc Không có"))[0]["code"] == "npc_not_found"
    cleared = await run_turn(env.a, single["id"], "/clearnpc")
    assert cleared[0]["code"] == "npc_cleared" and cleared[0]["detail"] == "1"

    # World chat: /time, /move, /addnpc, /removenpc mutate world state with StateEvent + manual tracking.
    world_chat = await _setup_world_chat(env)
    ev_time = await run_turn(env.a, world_chat["id"], "/time 21:30 Thứ Tư")
    assert _types(ev_time) == ["state", "notice", "done"]
    assert ev_time[1]["code"] == "time_updated" and ev_time[1]["detail"] == "21:30 Thứ Tư"
    assert ev_time[0]["state"]["time"] == "21:30 Thứ Tư" and "time" in ev_time[0]["state"]["manual"]

    ev_move = await run_turn(env.a, world_chat["id"], "/move sân thượng")
    assert _types(ev_move) == ["state", "notice", "done"]
    assert ev_move[1]["code"] == "location_moved" and ev_move[1]["detail"] == "Sân thượng"
    assert ev_move[0]["state"]["location_id"] == "san_thuong"

    ev_move_id = await run_turn(env.a, world_chat["id"], "/move can_tin")
    assert ev_move_id[0]["state"]["location_id"] == "can_tin"

    ev_bad_move = await run_turn(env.a, world_chat["id"], "/move nowhere")
    assert _types(ev_bad_move) == ["notice", "done"]
    assert ev_bad_move[0]["code"] == "move_target_unknown" and ev_bad_move[0]["detail"] == "nowhere"

    ev_npc_add = await run_turn(env.a, world_chat["id"], "/addnpc Bác bảo vệ - trực cổng")
    assert _types(ev_npc_add) == ["notice", "state", "done"]
    assert ev_npc_add[0]["code"] == "npc_added"
    assert ev_npc_add[1]["state"]["npcs"] == [{"name": "Bác bảo vệ", "age": None, "description": "trực cổng"}]

    ev_npc_rem = await run_turn(env.a, world_chat["id"], "/removenpc bác bảo vệ")
    assert _types(ev_npc_rem) == ["notice", "state", "done"]
    assert ev_npc_rem[0]["code"] == "npc_removed" and ev_npc_rem[1]["state"]["npcs"] == []
    assert len(await _messages(env.a, world_chat["id"])) == 1  # only the opening message


async def test_anti_repeat_rewrites_once_in_single_and_world_chats(env: ChatEnv) -> None:
    repeated = "Mai khẽ ngẩng đầu lên nhìn Nam qua quầy pha chế rồi nở một nụ cười rất dịu dàng."
    fresh = "Mai đặt tách trà vừa pha xuống bàn gỗ, nhẹ giọng hỏi về chuyến đi vừa rồi."

    char_id = await make_character(env.a, name="Mai", age=24, greetings=[repeated])
    chat = await make_chat(env.a, char_id)
    script_llm(env.llm, char_id, writer=[sse_stream(repeated), sse_stream(fresh)])

    events = await run_turn(env.a, chat["id"], "Chào Mai")
    kinds = _types(events)
    assert any(e["type"] == "notice" and e["code"] == "writer_repeated" for e in events)
    assert kinds.count("reset_content") == 1
    assert kinds.count("director") == 2 and kinds.count("rejudge") == 1

    writer_reqs = [r for r in env.llm.requests if _is_writer_req(r)]
    assert len(writer_reqs) == 2
    assert "Lần viết trước bị lặp nguyên văn tin trước".encode() in writer_reqs[1].content
    assert (await _messages(env.a, chat["id"]))[-1]["variants"][0]["content"] == fresh

    # World chat anti-repeat also filters <scene> cleanly on the rewrite.
    world_chat = await _setup_world_chat(env)
    opening_msg = (await _messages(env.a, world_chat["id"]))[0]["variants"][0]["content"]
    env.llm._fixtures.clear()
    _script_world_llm(
        env.llm,
        orchestrator_answers={
            "turn_type": {"choice": "dialogue", "confidence": 0.9, "probabilities": {"dialogue": 0.9}},
            "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "addressee": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "followup__han": {"noul": 0.1},
        },
        writer=[
            sse_stream(opening_msg + '\n<scene>{"env": {"old": "1"}}</scene>'),
            sse_stream('Vy vẫy tay gọi Nam lại gần bàn.\n<scene>{"env": {"sky": "trong"}}</scene>'),
        ],
    )
    w_events = await run_turn(env.a, world_chat["id"], "Chào Vy")
    assert any(e["type"] == "notice" and e["code"] == "writer_repeated" for e in w_events)
    assert any(e["type"] == "scene" and e["merged"]["env"].get("sky") == "trong" for e in w_events)
    assert (await _messages(env.a, world_chat["id"]))[-1]["variants"][0]["content"] == "Vy vẫy tay gọi Nam lại gần bàn."

    # World chat single_call anti-repeat also emits writer_repeated + reset_content(group) and splits rewritten prose.
    sc_chat = await _setup_world_chat(env, write_mode="single_call")
    sc_opening = (await _messages(env.a, sc_chat["id"]))[0]["variants"][0]["content"]
    env.llm._fixtures.clear()
    _script_world_llm(
        env.llm,
        orchestrator_answers={
            "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "followup__han": {"noul": 0.1},
        },
        writer=[
            sse_stream(sc_opening),
            sse_stream('[vy]: "Mình ra sân trước đi."\n<scene>{"env": {"breeze": "mát"}}</scene>'),
        ],
    )
    sc_events = await run_turn(env.a, sc_chat["id"], "Đi thôi")
    assert any(e["type"] == "notice" and e["code"] == "writer_repeated" for e in sc_events)
    assert any(e["type"] == "reset_content" and e["message_id"] == "group" for e in sc_events)
    assert (await _messages(env.a, sc_chat["id"]))[-1]["variants"][0]["content"] == '"Mình ra sân trước đi."'


async def test_continue_skips_answers_last_and_no_new_events_and_enforces_key_and_lock(
    env: ChatEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    char_id = await make_character(env.a, name="Mai", age=24)
    chat = await make_chat(env.a, char_id)

    # Director verdict that would FAIL answers_last & no_new_events unless skip_criteria skips them!
    continue_verdict = decision(
        {
            "answers_last": {"noul": 0.05},
            "no_new_events": {"noul": 0.95},
            "no_player_voice": {"noul": 0.02},
            "no_assistant_voice": {"noul": 0.01},
            "user_led": {"noul": 0.0},
            "priority": {"score": 1.0},
        }
    )
    script_llm(
        env.llm,
        char_id,
        writer=[sse_stream("Mai nhìn ra ngoài cửa sổ."), sse_stream("Cô khẽ nhấp ngụm trà.")],
        director=[continue_verdict],
    )

    # Empty body (no json) + prefill body both work without storing a user message.
    resp1 = await env.a.post(f"/api/chats/{chat['id']}/continue")
    assert resp1.status_code == 200, resp1.text
    ev1 = parse_sse(resp1.text)
    d1 = next(e for e in ev1 if e["type"] == "director")
    assert d1["passed"] is True
    assert {c["id"]: c["passed"] for c in d1["criteria"]} == {
        "answers_last": True,
        "no_new_events": True,
        "no_player_voice": True,
        "no_assistant_voice": True,
    }
    rows = await _messages(env.a, chat["id"])
    assert [(m["seq"], m["speaker"]) for m in rows] == [(0, char_id), (1, char_id)]
    assert rows[1]["meta"]["is_continue"] is True

    resp2 = await env.a.post(f"/api/chats/{chat['id']}/continue", json={"prefill": "*Khẽ cười*"})
    assert resp2.status_code == 200, resp2.text
    rows2 = await _messages(env.a, chat["id"])
    assert len(rows2) == 3 and all(m["speaker"] == char_id for m in rows2)
    last_writer = next(r for r in reversed(env.llm.requests) if _is_writer_req(r))
    assert "*Khẽ cười*" in last_writer.content.decode("utf-8")

    # World chat /continue also skips answers_last + no_new_events and passes empty user_message to Orchestrator.
    world_chat = await _setup_world_chat(env)
    env.llm._fixtures.clear()
    _script_world_llm(
        env.llm,
        orchestrator_answers={
            "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "followup__han": {"noul": 0.1},
        },
        writer=[sse_stream("Vy nhìn đồng hồ rồi mỉm cười.")],
        director=[continue_verdict],
    )
    w_cont = await env.a.post(f"/api/chats/{world_chat['id']}/continue", json={})
    assert w_cont.status_code == 200
    w_events = parse_sse(w_cont.text)
    assert next(e for e in w_events if e["type"] == "director")["passed"] is True
    assert len(await _messages(env.a, world_chat["id"])) == 2

    # Missing OpenRouter key -> 400 openrouter_key_missing.
    async def _no_secret(*_a: Any, **_kw: Any) -> str | None:
        return None

    monkeypatch.setattr("app.services.vault_service.get_secret", _no_secret)
    prev_kc = env.app.dependency_overrides.pop(get_key_check, None)
    prev_gw = env.app.dependency_overrides.pop(get_gateway_factory, None)
    try:

        def _dummy_sm() -> Any:
            class _Ctx:
                async def __aenter__(self) -> object:
                    return object()

                async def __aexit__(self, *_a: object) -> None:
                    return None

            return _Ctx()

        monkeypatch.setattr("app.core.deps.get_sessionmaker", lambda: _dummy_sm)
        assert ensure_openrouter_key is not None
        no_key = await env.a.post(f"/api/chats/{chat['id']}/continue")
        assert no_key.status_code == 400 and no_key.json()["error"]["code"] == "openrouter_key_missing"
    finally:
        if prev_kc is not None:
            env.app.dependency_overrides[get_key_check] = prev_kc
        if prev_gw is not None:
            env.app.dependency_overrides[get_gateway_factory] = prev_gw


async def test_regenerate_swipe_and_409_lock(env: ChatEnv) -> None:
    char_id = await make_character(env.a, name="Mai", age=24)
    chat = await make_chat(env.a, char_id)
    script_llm(
        env.llm,
        char_id,
        writer=[sse_stream("Lượt một gốc."), sse_stream("Lượt hai sẽ bị xoá."), sse_stream("Lượt một tạo lại.")],
    )
    await run_turn(env.a, chat["id"], "Tin 1")
    await run_turn(env.a, chat["id"], "Tin 2")
    before = await _messages(env.a, chat["id"])
    assert [m["seq"] for m in before] == [0, 1, 2, 3, 4]
    user_msg_id = before[1]["id"]
    ai1_id = before[2]["id"]

    # User message cannot be regenerated -> 422.
    bad_user = await env.a.post(f"/api/messages/{user_msg_id}/regenerate")
    assert bad_user.status_code == 422 and bad_user.json()["error"]["code"] == "cannot_regenerate_user_message"

    # Regenerate seq=2: rewinds seq > 2 (3 & 4 gone) and appends variant idx=1, active_variant=1.
    regen_resp = await env.a.post(f"/api/messages/{ai1_id}/regenerate")
    assert regen_resp.status_code == 200, regen_resp.text
    regen_events = parse_sse(regen_resp.text)
    start_ev = next(e for e in regen_events if e["type"] == "speaker_start")
    end_ev = next(e for e in regen_events if e["type"] == "speaker_end")
    assert start_ev["message_id"] == ai1_id and start_ev["seq"] == 2
    assert end_ev["message_id"] == ai1_id and end_ev["variant_idx"] == 1
    assert regen_events[-1] == {"type": "done", "message_ids": [ai1_id]}

    after = await _messages(env.a, chat["id"])
    assert [m["seq"] for m in after] == [0, 1, 2]
    assert after[2]["active_variant"] == 1
    assert [v["content"] for v in after[2]["variants"]] == ["Lượt một gốc.", "Lượt một tạo lại."]

    # Swipe via both /api/messages/{id}/active-variant and /api/chats/{cid}/messages/{id}/active-variant.
    sw1 = await env.a.put(f"/api/messages/{ai1_id}/active-variant", json={"variant_idx": 0})
    assert sw1.status_code == 200 and sw1.json()["active_variant"] == 0
    sw2 = await env.a.put(f"/api/chats/{chat['id']}/messages/{ai1_id}/active-variant", json={"variant_idx": 1})
    assert sw2.status_code == 200 and sw2.json()["active_variant"] == 1
    bad_sw = await env.a.put(f"/api/messages/{ai1_id}/active-variant", json={"variant_idx": 99})
    assert bad_sw.status_code == 422 and bad_sw.json()["error"]["code"] == "variant_not_found"

    # World chat regenerate via alias route updates <scene> + StateKeeper and prunes trailing snapshots!
    world_chat = await _setup_world_chat(env)
    env.llm._fixtures.clear()
    _script_world_llm(
        env.llm,
        orchestrator_answers={
            "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "followup__han": {"noul": 0.1},
        },
        writer=[
            sse_stream('Vy bản 1.\n<scene>{"env": {"mood": "1"}}</scene>'),
            sse_stream('Vy lượt 2.\n<scene>{"env": {"mood": "2"}}</scene>'),
            sse_stream('Vy bản 2.\n<scene>{"env": {"sky": "nắng"}}</scene>'),
        ],
    )
    await run_turn(env.a, world_chat["id"], "Chào Vy")
    await run_turn(env.a, world_chat["id"], "Lên sân thượng nhé")
    w_msgs = await _messages(env.a, world_chat["id"])
    vy_seq2_id = w_msgs[2]["id"]

    vault_id = uuid.UUID((await env.a.get("/api/vault/me")).json()["vault"]["id"])
    uow = env.app.dependency_overrides[get_unit_of_work]()
    async with uow() as r:
        await r.messages.add_snapshot(vault_id, parse_chat_id(world_chat["id"]), upto_seq=4, summary="Later", events=[])
        await r.commit()

    w_regen = await env.a.post(f"/api/chats/{world_chat['id']}/messages/{vy_seq2_id}/regenerate")
    assert w_regen.status_code == 200
    w_events = parse_sse(w_regen.text)
    assert "scene" in _types(w_events) and "state" in _types(w_events)
    assert next(e for e in w_events if e["type"] == "speaker_end")["variant_idx"] == 1
    async with uow() as r:
        assert await r.messages.list_snapshots(vault_id, parse_chat_id(world_chat["id"])) == []

    # Concurrent lock -> 409 turn_running on both /continue and /regenerate.
    gate, started = asyncio.Event(), asyncio.Event()
    inner = env.llm

    class _SlowBody(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield 'data: {"id":"g","choices":[{"delta":{"content":"Đang"},"finish_reason":null}]}\n\n'.encode()
            started.set()
            await gate.wait()
            yield 'data: {"id":"g","choices":[{"delta":{"content":" viết."},"finish_reason":"stop"}]}\n\n'.encode()
            yield b"data: [DONE]\n\n"

    def _handler(request: httpx.Request) -> httpx.Response:
        if _is_writer_req(request):
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=_SlowBody())
        return inner._handle(request)

    env.set_transport(httpx.MockTransport(_handler))
    task = asyncio.create_task(env.a.post(f"/api/chats/{chat['id']}/continue"))
    await asyncio.wait_for(started.wait(), timeout=10)
    conflict_cont = await env.a.post(f"/api/chats/{chat['id']}/continue")
    assert conflict_cont.status_code == 409 and conflict_cont.json()["error"]["code"] == "turn_running"
    conflict_regen = await env.a.post(f"/api/messages/{ai1_id}/regenerate")
    assert conflict_regen.status_code == 409 and conflict_regen.json()["error"]["code"] == "turn_running"
    gate.set()
    await asyncio.wait_for(task, timeout=10)


async def test_edit_delete_and_undo(env: ChatEnv) -> None:
    world_chat = await _setup_world_chat(env)
    _script_world_llm(
        env.llm,
        writer=[
            sse_stream('Vy chào lại.\n<scene>{"env": {"light": "sáng"}}</scene>'),
            sse_stream("Hân mỉm cười."),
            sse_stream("Vy nói tiếp."),
            sse_stream("Hân gật đầu."),
        ],
    )
    await run_turn(env.a, world_chat["id"], "Chào hai cậu")  # seq 0..3 (1:user, 2:vy, 3:han)
    await run_turn(env.a, world_chat["id"], "Đi ăn không?")  # seq 4..6 (4:user, 5:vy, 6:han)
    msgs = await _messages(env.a, world_chat["id"])
    assert [m["seq"] for m in msgs] == [0, 1, 2, 3, 4, 5, 6]

    # Edit active variant via both routes.
    ed1 = await env.a.patch(f"/api/messages/{msgs[2]['id']}", json={"content": "Vy đã sửa lời."})
    assert ed1.status_code == 200 and ed1.json()["variants"][0]["content"] == "Vy đã sửa lời."
    ed2 = await env.a.patch(f"/api/chats/{world_chat['id']}/messages/{msgs[3]['id']}", json={"content": "Hân đã sửa."})
    assert ed2.status_code == 200 and ed2.json()["variants"][0]["content"] == "Hân đã sửa."

    # Cannot delete seq=0 greeting -> 422 cannot_delete_greeting.
    del_zero = await env.a.delete(f"/api/messages/{msgs[0]['id']}")
    assert del_zero.status_code == 422 and del_zero.json()["error"]["code"] == "cannot_delete_greeting"

    # Undo removes last user turn + following AI messages (seq 4, 5, 6 -> removed_count=3) and restores state!
    undo1 = await env.a.post(f"/api/chats/{world_chat['id']}/undo")
    assert undo1.status_code == 200, undo1.text
    assert undo1.json()["removed_count"] == 3
    assert undo1.json()["chat"]["messages_count"] == 4
    assert [m["seq"] for m in await _messages(env.a, world_chat["id"])] == [0, 1, 2, 3]

    # Add a snapshot at upto_seq=3 and delete from seq=2 -> removes seq 2, 3 (count=2) and prunes snapshot!
    vault_id = uuid.UUID((await env.a.get("/api/vault/me")).json()["vault"]["id"])
    uow = env.app.dependency_overrides[get_unit_of_work]()
    async with uow() as r:
        await r.messages.add_snapshot(vault_id, parse_chat_id(world_chat["id"]), upto_seq=3, summary="S3", events=[])
        await r.commit()

    del2 = await env.a.delete(f"/api/chats/{world_chat['id']}/messages/{msgs[2]['id']}")
    assert del2.status_code == 200 and del2.json()["removed_count"] == 2
    assert del2.json()["chat"]["messages_count"] == 2
    assert del2.json()["chat"]["state"]["location_id"] == "can_tin"  # restored from seq=2 state_before!
    async with uow() as r:
        assert await r.messages.list_snapshots(vault_id, parse_chat_id(world_chat["id"])) == []

    # Undo the remaining user message (seq=1) -> removed_count=1, then undo again -> 422 nothing_to_undo!
    undo2 = await env.a.post(f"/api/chats/{world_chat['id']}/undo")
    assert undo2.status_code == 200 and undo2.json()["removed_count"] == 1
    undo_empty = await env.a.post(f"/api/chats/{world_chat['id']}/undo")
    assert undo_empty.status_code == 422 and undo_empty.json()["error"]["code"] == "nothing_to_undo"

    # Continue after greeting (no user msg >= 1) -> undo removes that single AI continuation!
    cont_resp = await env.a.post(f"/api/chats/{world_chat['id']}/continue")
    assert cont_resp.status_code == 200
    assert len(await _messages(env.a, world_chat["id"])) >= 2
    undo_cont = await env.a.post(f"/api/chats/{world_chat['id']}/undo")
    assert undo_cont.status_code == 200 and undo_cont.json()["removed_count"] >= 1
    assert len(await _messages(env.a, world_chat["id"])) == 1


async def test_fork_copies_messages_variants_snapshots_and_state_before(env: ChatEnv) -> None:
    char_id = await make_character(env.a, name="Mai", age=24, greetings=["Chào {{user}}."])
    persona_id = await make_persona(env.a, name="Nam")
    chat = await make_chat(env.a, char_id, persona_id=persona_id, title="Gốc")

    script_llm(
        env.llm,
        char_id,
        writer=[
            sse_stream("Mai trả lời lần 1."),
            sse_stream("Mai trả lời lần 1 bản 2."),
            sse_stream("Mai trả lời lượt 2."),
        ],
    )
    env.llm.add(
        [_archivist_response("- Mai và Nam nói chuyện ở quán.", [("Hẹn gặp", "Mai hẹn Nam tối mai.")])],
        {"path": COMPLETIONS, "stream": False, "contains": "archivist"},
        name="archivist",
    )

    await run_turn(env.a, chat["id"], "Tin 1")  # seq 1, 2
    msgs1 = await _messages(env.a, chat["id"])
    seq2_id = msgs1[2]["id"]
    await env.a.post(f"/api/messages/{seq2_id}/regenerate")  # seq=2 now has 2 variants, active=1
    await run_turn(env.a, chat["id"], "Tin 2")  # seq 3, 4

    # Add two snapshots: one at upto_seq=3 (valid for fork at seq=2) and one at upto_seq=5 (must NOT be copied).
    vault_id = uuid.UUID((await env.a.get("/api/vault/me")).json()["vault"]["id"])
    uow = env.app.dependency_overrides[get_unit_of_work]()
    async with uow() as r:
        await r.messages.add_snapshot(vault_id, parse_chat_id(chat["id"]), upto_seq=3, summary="Snap3", events=[])
        await r.messages.add_snapshot(vault_id, parse_chat_id(chat["id"]), upto_seq=5, summary="Snap5", events=[])
        await r.commit()

    # Fork at seq=2 (by message_id): copies seq 0..2 with all variants, snapshot upto_seq<=3, and seq=3's state_before.
    fork_mid = await env.a.post(f"/api/chats/{chat['id']}/fork", json={"message_id": seq2_id, "title": "Nhánh 1"})
    assert fork_mid.status_code == 201, fork_mid.text
    child = fork_mid.json()
    assert child["parent_chat_id"] == chat["id"]
    assert child["forked_at_seq"] == 2
    assert child["title"] == "Nhánh 1"
    assert child["messages_count"] == 3

    child_msgs = await _messages(env.a, child["id"])
    assert [m["seq"] for m in child_msgs] == [0, 1, 2]
    assert child_msgs[2]["active_variant"] == 1
    assert [v["content"] for v in child_msgs[2]["variants"]] == ["Mai trả lời lần 1.", "Mai trả lời lần 1 bản 2."]

    async with uow() as r:
        parent_rows = await r.messages.page(vault_id, parse_chat_id(chat["id"]), before=None, limit=10)
        child_snaps = await r.messages.list_snapshots(vault_id, parse_chat_id(child["id"]))
    assert child["state"] == parent_rows[3].state_before
    assert [s.upto_seq for s in child_snaps] == [3]

    # Listing chats exposes parent_chat_id & forked_at_seq.
    listed = {c["id"]: c for c in (await env.a.get("/api/chats")).json()}
    assert listed[child["id"]]["parent_chat_id"] == chat["id"]
    assert listed[child["id"]]["forked_at_seq"] == 2

    # Fork at end (no body) copies everything and matches current chat state.
    fork_end = await env.a.post(f"/api/chats/{chat['id']}/fork")
    assert fork_end.status_code == 201
    assert fork_end.json()["forked_at_seq"] == 4 and fork_end.json()["messages_count"] == 5

    # Out-of-range upto_seq -> 422; message from another chat -> 404.
    bad_seq = await env.a.post(f"/api/chats/{chat['id']}/fork", json={"upto_seq": 99})
    assert bad_seq.status_code == 422 and bad_seq.json()["error"]["code"] == "validation_error"
    other_chat = await make_chat(env.a, char_id)
    other_msg_id = (await _messages(env.a, other_chat["id"]))[0]["id"]
    wrong_msg = await env.a.post(f"/api/chats/{chat['id']}/fork", json={"message_id": other_msg_id})
    assert wrong_msg.status_code == 404 and wrong_msg.json()["error"]["code"] == "message_not_found"


async def test_vault_isolation_on_all_p5_endpoints(env: ChatEnv) -> None:
    char_id = await make_character(env.a, name="Mai", age=24)
    chat = await make_chat(env.a, char_id)
    other_chat = await make_chat(env.a, char_id)
    script_llm(env.llm, char_id, writer=[sse_stream("Mai gật đầu.")])
    await run_turn(env.a, chat["id"], "Chào Mai")
    msgs = await _messages(env.a, chat["id"])
    cid = chat["id"]
    mid = msgs[-1]["id"]

    # Cross-vault checks (Vault B -> 404 on every new route).
    b_checks: list[tuple[str, str, dict[str, Any]]] = [
        ("POST", f"/api/chats/{cid}/continue", {}),
        ("POST", f"/api/chats/{cid}/undo", {}),
        ("POST", f"/api/chats/{cid}/fork", {"json": {}}),
        ("PUT", f"/api/messages/{mid}/active-variant", {"json": {"variant_idx": 0}}),
        ("PUT", f"/api/chats/{cid}/messages/{mid}/active-variant", {"json": {"variant_idx": 0}}),
        ("PATCH", f"/api/messages/{mid}", {"json": {"content": "hacked"}}),
        ("PATCH", f"/api/chats/{cid}/messages/{mid}", {"json": {"content": "hacked"}}),
        ("DELETE", f"/api/messages/{mid}", {}),
        ("DELETE", f"/api/chats/{cid}/messages/{mid}", {}),
        ("POST", f"/api/messages/{mid}/regenerate", {}),
        ("POST", f"/api/chats/{cid}/messages/{mid}/regenerate", {}),
    ]
    for method, path, kwargs in b_checks:
        resp = await env.b.request(method, path, **kwargs)
        assert resp.status_code == 404, (method, path, resp.text)

    # Same-vault chat/message mismatch on scoped alias routes -> 404 message_not_found.
    mismatch_checks: list[tuple[str, str, dict[str, Any]]] = [
        ("PUT", f"/api/chats/{other_chat['id']}/messages/{mid}/active-variant", {"json": {"variant_idx": 0}}),
        ("PATCH", f"/api/chats/{other_chat['id']}/messages/{mid}", {"json": {"content": "x"}}),
        ("DELETE", f"/api/chats/{other_chat['id']}/messages/{mid}", {}),
        ("POST", f"/api/chats/{other_chat['id']}/messages/{mid}/regenerate", {}),
    ]
    for method, path, kwargs in mismatch_checks:
        resp = await env.a.request(method, path, **kwargs)
        assert resp.status_code == 404 and resp.json()["error"]["code"] == "message_not_found"
