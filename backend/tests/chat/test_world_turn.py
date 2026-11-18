"""World-chat turn pipeline tests: per_character, single_call, <scene>, Director, stop, /force, and fallbacks."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.agents.orchestrator import WorldPlannedSpeaker
from app.formats.card import VietrpCard
from app.llm.fake import RecordedLLM, _Fixture
from app.pipeline.world_assembly import WorldCastEntry
from app.pipeline.world_turn import parse_single_call_segments
from app.services.chat_service import get_unit_of_work, parse_chat_id
from tests.chat.conftest import (
    COMPLETIONS,
    DECISIONS,
    DIRECTOR_PASS,
    ChatEnv,
    decision,
    director_fail,
    make_character,
    make_persona,
    parse_sse,
    run_turn,
    sse_stream,
)
from tests.chat.test_world_chat import make_world, make_world_chat

EXTRACTIONS = "/api/alpha/extractions"


def types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def is_writer_request(request: httpx.Request) -> bool:
    return request.url.path == COMPLETIONS and b'"stream":true' in request.content.replace(b" ", b"")


async def _messages(env: ChatEnv, chat_id: str, suffix: str = "") -> list[dict[str, Any]]:
    resp = await env.a.get(f"/api/chats/{chat_id}/messages{suffix}")
    assert resp.status_code == 200
    result: list[dict[str, Any]] = resp.json()
    return result


def _extraction_time(value: str = "10:15", confidence: float = 0.9) -> dict[str, Any]:
    return {
        "status": 200,
        "json": {
            "model": "google/gemini-2.5-flash",
            "usage": {"prompt_tokens": 30, "completion_tokens": 5, "cost": 0.0001},
            "answers": {"time": {"value": value, "confidence": confidence}},
        },
    }


def _script_world_llm(
    llm: RecordedLLM,
    *,
    writer: list[dict[str, Any]],
    director: list[dict[str, Any]] | None = None,
    orchestrator_answers: dict[str, Any] | None = None,
    state_keeper_answers: dict[str, Any] | None = None,
    time_value: str = "10:15",
) -> None:
    bond_json = {
        "pairs": {
            "vy:user": [
                {"addressing": "override-ignored", "nickname": "Cậu bạn", "stance": "nhiệt tình", "closeness": 2},
                {"addressing": "override-2", "nickname": "Nam ơi", "stance": "vui vẻ", "closeness": 3},
            ],
            "han:user": [
                {"addressing": "tôi - cậu", "relationship": "bạn cùng lớp", "stance": "điềm tĩnh", "closeness": 1},
                {"addressing": "mình - cậu", "relationship": "bạn cùng bàn", "stance": "dịu dàng", "closeness": 2},
            ],
            "vy:han": [
                {"nickname": "Hân kính cận", "stance": "thân mật", "closeness": 4},
            ],
            "han:vy": [
                {"addressing": "tao - mày", "relationship": "bạn thân", "stance": "tin cậy", "closeness": 4},
            ],
            "le_minh_tuan:user": [
                {"addressing": "ông - tui", "relationship": "bạn cùng khối", "stance": "hòa đồng", "closeness": 1},
            ],
            "vy:le_minh_tuan": [
                {"addressing": "cậu - tớ", "relationship": "đồng đội", "stance": "thoải mái", "closeness": 2}
            ],
            "le_minh_tuan:vy": [
                {"addressing": "tớ - cậu", "relationship": "bạn học", "stance": "tôn trọng", "closeness": 2}
            ],
            "han:le_minh_tuan": [
                {"addressing": "tôi - cậu", "relationship": "quen biết", "stance": "lịch sự", "closeness": 1}
            ],
            "le_minh_tuan:han": [
                {"addressing": "tôi - cậu", "relationship": "quen biết", "stance": "lịch sự", "closeness": 1}
            ],
        }
    }
    llm.add(
        [
            {
                "status": 200,
                "json": {
                    "choices": [{"message": {"role": "assistant", "content": json.dumps(bond_json)}}],
                    "usage": {"prompt_tokens": 90, "completion_tokens": 40},
                },
            }
        ],
        {"path": COMPLETIONS, "stream": False, "contains": "vy:user"},
        name="world_bond_drafter",
    )
    llm.add(
        [
            decision(
                {
                    "bond__0": {"choice": "2", "confidence": 0.8, "probabilities": {"1": 0.2, "2": 0.8}},
                    "bond__1": {"choice": "2", "confidence": 0.85, "probabilities": {"1": 0.15, "2": 0.85}},
                }
            )
        ],
        {"path": DECISIONS, "contains": "bond__0"},
        name="world_bond_selector",
    )
    orch_base: dict[str, Any] = {
        "turn_type": {"choice": "dialogue", "confidence": 0.9, "probabilities": {"dialogue": 0.9}},
        "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9, "han": 0.4}},
        "addressee": {"choice": "vy", "confidence": 0.8, "probabilities": {"vy": 0.8}},
        "arrive__le_minh_tuan": {"noul": 0.1},
        "followup__vy": {"noul": 0.1},
        "followup__han": {"noul": 0.75},
        "followup__le_minh_tuan": {"noul": 0.1},
        "secret__vy__s1": {"noul": 0.9},
        "secret__han__s1": {"noul": 0.1},
    }
    if orchestrator_answers is not None:
        orch_base.update(orchestrator_answers)
    llm.add([decision(orch_base)], {"path": DECISIONS, "contains": "turn_type"}, name="world_orchestrator")
    llm.add(director or [DIRECTOR_PASS], {"path": DECISIONS, "contains": "answers_last"}, name="director")
    sk_base: dict[str, Any] = {
        "present__vy": {"noul": 0.8},
        "present__han": {"noul": 0.7},
        "present__le_minh_tuan": {"noul": 0.65},
        "location": {"choice": "san_thuong", "confidence": 0.85, "probabilities": {"san_thuong": 0.85}},
        "tension": {"score": 2.0},
        "interject__vy": {"noul": 0.3},
        "interject__han": {"noul": 0.3},
        "interject__le_minh_tuan": {"noul": 0.3},
    }
    if state_keeper_answers is not None:
        sk_base.update(state_keeper_answers)
    llm.add([decision(sk_base)], {"path": DECISIONS, "contains": "present__"}, name="state_keeper_decisions")
    llm.add([_extraction_time(time_value)], {"path": EXTRACTIONS}, name="state_keeper_time")
    llm.add(writer, {"path": COMPLETIONS, "stream": True}, name="writer")


async def _setup_cast_and_chat(
    env: ChatEnv,
    *,
    settings: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    vy_id = await make_character(
        env.a,
        name="Trần Hạ Vy",
        age=20,
        tagline="Lớp phó",
        addressing={"user": "tôi - cậu", "by_character": {"han": "mày - tao"}},
        relationships={"by_character": {"han": "bạn thân"}},
        secrets=[{"id": "s1", "content": "SECRET_VY_S1", "reveal_when": "khi được hỏi"}],
    )
    han_id = await make_character(
        env.a,
        name="Nguyễn Gia Hân",
        age=21,
        tagline="Thư viện trưởng",
        secrets=[{"id": "s1", "content": "SECRET_HAN_HIDDEN", "reveal_when": "không bao giờ"}],
    )
    tuan_id = await make_character(env.a, name="Lê Minh Tuấn", age=22, tagline="Đội trưởng")
    world_id = await make_world(env.a)
    persona_id = await make_persona(env.a, name="Nam")
    chat = await make_world_chat(
        env.a,
        world_id,
        "gio_ra_choi",
        [vy_id, han_id, tuan_id],
        persona_id=persona_id,
        settings=settings,
    )
    return chat, {"vy": vy_id, "han": han_id, "tuan": tuan_id}


async def test_world_turn_per_character_multi_speaker_scene_bonds_and_state(env: ChatEnv) -> None:
    chat, _ = await _setup_cast_and_chat(env)
    vy_scene = json.dumps(
        {
            "env": {"weather": "mưa nhẹ"},
            "chars": {"vy": {"mood": "vui", "holding": "trà đào"}, "han": {"mood": "bị chặn"}},
            "items": ["ô đỏ"],
        },
        ensure_ascii=False,
    )
    han_scene = '{"chars": {"han": {"mood": "tò mò", "pose": "nghiêng đầu"}}}'
    _script_world_llm(
        env.llm,
        writer=[
            # Split `<scene` right across streaming chunks!
            sse_stream('Vy cười tươi: "Lên sân thượng nhé!"\n\n<sc', f"ene>{vy_scene}</scene>"),
            sse_stream('Hân gật đầu: "Đi thôi."<scene>', f"{han_scene}</scene>"),
            sse_stream("Lượt hai của Vy."),
        ],
    )

    events = await run_turn(env.a, chat["id"], "Hai cậu lên sân thượng hóng gió không?")
    kinds = types(events)

    assert kinds.index("bonds") < kinds.index("plan") < kinds.index("speaker_start")
    assert kinds.index("scene") < kinds.index("speaker_end")
    assert kinds.index("state") < kinds.index("done")
    assert [e["speaker"] for e in events if e["type"] == "speaker_start"] == ["vy", "han"]
    assert kinds.count("scene") == 2

    # `<scene` MUST NEVER leak into draft or content events!
    drafted_text = "".join(e["delta"] for e in events if e["type"] == "draft")
    assert "<scene" not in drafted_text and "<sc" not in drafted_text
    assert "SECRET_VY_S1" not in drafted_text

    # Director NEVER sees `<scene>` blocks!
    director_reqs = [r for r in env.llm.requests_to(DECISIONS) if b"answers_last" in r.content]
    assert len(director_reqs) == 2
    assert all(b"<scene" not in req.content and b"m\\u01b0a" not in req.content for req in director_reqs)

    # Writer requests: vy got SECRET_VY_S1; han saw vy's prose (without <scene>) and did NOT get SECRET_HAN_HIDDEN!
    writer_reqs = [r for r in env.llm.requests if is_writer_request(r)]
    assert len(writer_reqs) == 2
    assert b"SECRET_VY_S1" in writer_reqs[0].content
    assert b"SECRET_HAN_HIDDEN" not in writer_reqs[1].content
    han_msgs = json.loads(writer_reqs[1].content)["messages"]
    han_history = [m["content"] for m in han_msgs if m["role"] == "assistant"]
    assert any('Lên sân thượng nhé!"' in msg and "<scene" not in msg for msg in han_history)

    # Scene merge respected per_character ownership: vy could not mutate han's mood, han updated her own mood.
    state_ev = next(e for e in events if e["type"] == "state")
    assert state_ev["state"]["location_id"] == "san_thuong"
    assert state_ev["state"]["tension"] == 2
    assert state_ev["state"]["present_ids"] == ["vy", "han", "le_minh_tuan"]
    assert state_ev["state"]["time"] == "10:15 Thứ Hai"  # keep_day preserved Thứ Hai
    assert state_ev["state"]["scene"]["env"] == {"weather": "mưa nhẹ"}
    assert state_ev["state"]["scene"]["chars"]["vy"]["mood"] == "vui"
    assert state_ev["state"]["scene"]["chars"]["vy"]["holding"] == "trà đào"
    assert state_ev["state"]["scene"]["chars"]["han"]["mood"] == "tò mò"
    assert state_ev["state"]["scene"]["chars"]["han"]["pose"] == "nghiêng đầu"
    assert state_ev["state"]["scene"]["items"] == ["ô đỏ"]
    assert "vy:user" in state_ev["state"]["bonds"]
    assert state_ev["state"]["bonds"]["vy:user"]["fields"]["addressing"] == "tôi - cậu"  # seq=0 pin preserved!
    assert state_ev["state"]["bonds"]["vy:user"]["fields"]["nickname"] == "Nam ơi"  # option 2 filled gap!

    # Persisted messages + state_before
    rows = await _messages(env, chat["id"])
    assert [(m["seq"], m["speaker"]) for m in rows] == [
        (0, "narrator"),
        (1, "user"),
        (2, "vy"),
        (3, "han"),
    ]
    assert rows[2]["variants"][0]["content"] == 'Vy cười tươi: "Lên sân thượng nhé!"'
    assert rows[2]["meta"]["scene_delta"]["items"] == ["ô đỏ"]
    assert rows[3]["variants"][0]["content"] == 'Hân gật đầu: "Đi thôi."'

    vault_id = uuid.UUID((await env.a.get("/api/vault/me")).json()["vault"]["id"])
    uow = env.app.dependency_overrides[get_unit_of_work]()
    async with uow() as r:
        db_msgs = await r.messages.page(vault_id, parse_chat_id(chat["id"]), before=None, limit=10)
    assert db_msgs[2].state_before is not None and db_msgs[2].state_before["scene"]["chars"] == {}
    assert db_msgs[3].state_before is not None and "vy" in db_msgs[3].state_before["scene"]["chars"]

    # Turn 2 does NOT re-run bond_drafter or bond_selector.
    before_reqs = len(env.llm.requests)
    turn2 = await run_turn(env.a, chat["id"], "Mát quá!")
    assert "bonds" not in types(turn2)
    assert not any(
        r.url.path == COMPLETIONS and b'"stream":false' in r.content.replace(b" ", b"")
        for r in env.llm.requests[before_reqs:]
    )


async def test_world_turn_broken_scene_notice_and_director_best_attempt_keeps_matching_scene(env: ChatEnv) -> None:
    chat, _ = await _setup_cast_and_chat(env)
    # 1. Broken <scene> emits scene_parse_failed notice; Director retries strip <scene>.
    _script_world_llm(
        env.llm,
        orchestrator_answers={
            "turn_type": {"choice": "dialogue", "confidence": 0.9, "probabilities": {"dialogue": 0.9}},
            "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "addressee": {"choice": "vy", "confidence": 0.8, "probabilities": {"vy": 0.8}},
            "followup__han": {"noul": 0.1},
        },
        writer=[
            sse_stream("Nháp lỗi.\n<scene>{not valid</scene>"),
            sse_stream("Bản sửa ổn.\n<scene>{still broken</scene>"),
            # Turn 2: 3 failed verdicts -> attempt 0 scores higher (0.875) -> keeps attempt 0 + its scene.
            sse_stream('Tốt nhất.\n<scene>{"env": {"sky": "trong xanh"}}</scene>'),
            sse_stream('Kém hơn.\n<scene>{"env": {"sky": "âm u"}}</scene>'),
            sse_stream('Kém nhất.\n<scene>{"env": {"sky": "bão"}}</scene>'),
        ],
        director=[
            director_fail(0.6),
            DIRECTOR_PASS,
            director_fail(0.5),
            director_fail(0.7),
            director_fail(0.9),
        ],
    )
    ev1 = await run_turn(env.a, chat["id"], "Chào Vy")
    assert any(e["type"] == "notice" and e["code"] == "scene_parse_failed" for e in ev1)
    assert (await _messages(env, chat["id"]))[-1]["variants"][0]["content"] == "Bản sửa ổn."

    ev2 = await run_turn(env.a, chat["id"], "Nhìn bầu trời đi")
    assert any(e["type"] == "scene" and e["merged"]["env"].get("sky") == "trong xanh" for e in ev2)
    assert (await _messages(env, chat["id"]))[-1]["variants"][0]["content"] == "Tốt nhất."


async def test_world_turn_hold_until_approved_and_stop_cancellation(env: ChatEnv) -> None:
    chat, _ = await _setup_cast_and_chat(env, settings={"director": {"stream_mode": "hold_until_approved"}})
    _script_world_llm(
        env.llm,
        orchestrator_answers={
            "turn_type": {"choice": "dialogue", "confidence": 0.9, "probabilities": {"dialogue": 0.9}},
            "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "addressee": {"choice": "vy", "confidence": 0.8, "probabilities": {"vy": 0.8}},
            "followup__han": {"noul": 0.1},
        },
        writer=[
            sse_stream("Nháp một.\n<scene>{}</scene>"),
            sse_stream('Bản duyệt.\n<scene>{"env": {"wind": "nhẹ"}}</scene>'),
        ],
        director=[director_fail(), DIRECTOR_PASS],
    )
    events = await run_turn(env.a, chat["id"], "Chào")
    kinds = types(events)
    assert "draft" not in kinds and "reset_content" not in kinds
    content_deltas = [e["delta"] for e in events if e["type"] == "content"]
    assert content_deltas == ["Bản duyệt."]
    assert kinds.index("content") > max(i for i, k in enumerate(kinds) if k == "director")

    # Stop mid-speaker stream: saves partial variant and skips State Keeper!
    class GatedBody(httpx.AsyncByteStream):
        def __init__(self, first: bytes, second: bytes, gate: asyncio.Event, started: asyncio.Event) -> None:
            self._parts = (first, second)
            self._gate = gate
            self._started = started

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield self._parts[0]
            self._started.set()
            await self._gate.wait()
            yield self._parts[1]

    def chunk(text: str) -> bytes:
        payload = json.dumps({"id": "g", "choices": [{"delta": {"content": text}, "finish_reason": None}]})
        return f"data: {payload}\n\n".encode()

    gate, started = asyncio.Event(), asyncio.Event()
    inner = env.llm

    def handler(request: httpx.Request) -> httpx.Response:
        if is_writer_request(request):
            body = GatedBody(
                chunk("Phần đầu bị dừng."), chunk("Phần sau.<scene>{}</scene>") + b"data: [DONE]\n\n", gate, started
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)
        return inner._handle(request)

    env.set_transport(httpx.MockTransport(handler))
    task = asyncio.create_task(env.a.post(f"/api/chats/{chat['id']}/turn", json={"text": "Kể tiếp đi"}))
    await asyncio.wait_for(started.wait(), timeout=10)
    assert (await env.a.post(f"/api/chats/{chat['id']}/stop")).json() == {"stopped": True}
    gate.set()
    resp = await asyncio.wait_for(task, timeout=10)
    stop_events = parse_sse(resp.text)
    end = next(e for e in stop_events if e["type"] == "speaker_end")
    assert end["stopped"] is True
    assert "state" not in types(stop_events)  # State Keeper skipped when stopped mid-turn!
    last_msg = (await _messages(env, chat["id"]))[-1]
    assert last_msg["variants"][0]["stopped"] is True
    assert last_msg["variants"][0]["content"] == "Phần đầu bị dừng."


async def test_world_turn_single_call_splits_speakers_and_merges_scene(env: ChatEnv) -> None:
    chat, _ = await _setup_cast_and_chat(env, settings={"group": {"write_mode": "single_call"}})
    combined = (
        '[vy]: "Cậu tới rồi à?"\n'
        'Nguyễn Gia Hân: "Chờ lâu chưa?"\n'
        "Người dẫn truyện: Chuông trường vang lên.\n"
        '<scene>{"env": {"ambience": "ồn ào"}, "chars": {"vy": {"mood": "vui"}, "han": {"mood": "bình tĩnh"}}}</scene>'
    )
    _script_world_llm(env.llm, writer=[sse_stream(combined)])

    events = await run_turn(env.a, chat["id"], "Mình tới rồi đây!")
    kinds = types(events)
    assert [e["speaker"] for e in events if e["type"] == "speaker_start"] == ["vy", "han", "narrator"]
    assert [e["delta"] for e in events if e["type"] == "content"] == [
        '"Cậu tới rồi à?"',
        '"Chờ lâu chưa?"',
        "Chuông trường vang lên.",
    ]
    assert kinds.count("scene") == 1
    assert kinds.index("state") < kinds.index("done")

    scene_ev = next(e for e in events if e["type"] == "scene")
    assert scene_ev["merged"]["chars"]["vy"]["mood"] == "vui"
    assert scene_ev["merged"]["chars"]["han"]["mood"] == "bình tĩnh"
    assert scene_ev["merged"]["env"]["ambience"] == "ồn ào"

    rows = await _messages(env, chat["id"])
    assert [(r["seq"], r["speaker"], r["variants"][0]["content"]) for r in rows] == [
        (0, "narrator", "Chuông vừa reo, Nam bước vào căn tin."),
        (1, "user", "Mình tới rồi đây!"),
        (2, "vy", '"Cậu tới rồi à?"'),
        (3, "han", '"Chờ lâu chưa?"'),
        (4, "narrator", "Chuông trường vang lên."),
    ]
    assert rows[4]["meta"]["scene_delta"]["env"] == {"ambience": "ồn ào"}


def test_parse_single_call_segments_variants() -> None:
    cast = [
        WorldCastEntry("vy", VietrpCard(name="Trần Hạ Vy", age=20, aliases=["Lớp phó"])),
        WorldCastEntry("han", VietrpCard(name="Nguyễn Gia Hân", age=21)),
    ]
    planned = [WorldPlannedSpeaker(id="vy", kind="character", sentences=4, order=0)]

    # [id], id:, **Name**:, consecutive same speaker merged
    parsed = parse_single_call_segments(
        "[vy]\nCâu 1.\nvy: Câu 2.\n**Nguyễn Gia Hân**: Câu 3.\nNgười dẫn truyện: Khép lại.",
        cast,
        planned,
    )
    assert parsed == [
        ("vy", "Câu 1.\nCâu 2."),
        ("han", "Câu 3."),
        ("narrator", "Khép lại."),
    ]

    # Fallback to first planned speaker when no headers match
    assert parse_single_call_segments("Chỉ có một đoạn văn.", cast, planned) == [("vy", "Chỉ có một đoạn văn.")]


async def test_world_turn_commands_force_and_non_critical_failures(env: ChatEnv) -> None:
    chat, _ = await _setup_cast_and_chat(env)
    _script_world_llm(env.llm, writer=[sse_stream("Tuấn chạy vào."), sse_stream("Vy nhìn sang.")])

    # `/time` command updates state directly without saving a message or calling LLMs
    timed = await run_turn(env.a, chat["id"], "/time 15:00")
    assert types(timed) == ["state", "notice", "done"]
    assert timed[0]["state"]["time"] == "15:00"
    assert timed[1]["code"] == "time_updated"
    assert len(await _messages(env, chat["id"])) == 1

    # /force @tuan (currently absent) forces le_minh_tuan as speaker 0 with arriving_ids containing le_minh_tuan
    forced = await run_turn(env.a, chat["id"], "/force @tuan Cậu ở đâu thế?")
    plan_ev = next(e for e in forced if e["type"] == "plan")
    assert plan_ev["speakers"][0]["id"] == "le_minh_tuan" and plan_ev["speakers"][0]["reason"] == "forced"

    # Unknown /force target emits notice and proceeds
    unknown = await run_turn(env.a, chat["id"], "/force @ai_do Chào")
    assert any(e["type"] == "notice" and e["code"] == "force_target_unknown" for e in unknown)

    # Non-critical State Keeper + Director failure emits notices and completes turn
    env.llm._fixtures.insert(
        0, _Fixture("dir_down", {"path": DECISIONS, "contains": "answers_last"}, [{"status": 400, "json": {}}])
    )
    env.llm._fixtures.insert(
        0, _Fixture("sk_down", {"path": DECISIONS, "contains": "present__"}, [{"status": 400, "json": {}}])
    )
    degraded = await run_turn(env.a, chat["id"], "Mọi người ổn chứ?")
    notices = {e["code"] for e in degraded if e["type"] == "notice"}
    assert "director_failed" in notices and "state_keeper_failed" in notices
    assert degraded[-1]["type"] == "done"


async def test_world_turn_single_call_retry_and_stop_mid_scene_skips_parse_notice(env: ChatEnv) -> None:
    single_chat, _ = await _setup_cast_and_chat(env, settings={"group": {"write_mode": "single_call"}})
    _script_world_llm(
        env.llm,
        writer=[
            sse_stream('vy: "Bản nháp hỏng."\n<scene>{}</scene>'),
            sse_stream('vy: "Bản đã sửa."\n<scene>{"env": {"sky": "đẹp"}}</scene>'),
        ],
        director=[director_fail(), DIRECTOR_PASS],
    )
    retry_events = await run_turn(env.a, single_chat["id"], "Chào Vy")
    assert any(e["type"] == "reset_content" and e["message_id"] == "group" for e in retry_events)
    assert any(e["type"] == "draft" for e in retry_events)
    assert [e["delta"] for e in retry_events if e["type"] == "content"] == ['"Bản đã sửa."']

    # Stopping mid-<scene tag must not emit a bogus scene_parse_failed notice.
    per_char_chat, _ = await _setup_cast_and_chat(env)
    _script_world_llm(env.llm, writer=[sse_stream("unused")])

    class GatedBody(httpx.AsyncByteStream):
        def __init__(self, first: bytes, second: bytes, gate: asyncio.Event, started: asyncio.Event) -> None:
            self._parts = (first, second)
            self._gate = gate
            self._started = started

        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield self._parts[0]
            self._started.set()
            await self._gate.wait()
            yield self._parts[1]

    def chunk(text: str) -> bytes:
        payload = json.dumps({"id": "g", "choices": [{"delta": {"content": text}, "finish_reason": None}]})
        return f"data: {payload}\n\n".encode()

    gate, started = asyncio.Event(), asyncio.Event()
    inner = env.llm

    def handler(request: httpx.Request) -> httpx.Response:
        if is_writer_request(request):
            body = GatedBody(
                chunk('Phần đầu.<scene>{"broken'),
                chunk('": 1}</scene>') + b"data: [DONE]\n\n",
                gate,
                started,
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)
        return inner._handle(request)

    env.set_transport(httpx.MockTransport(handler))
    task = asyncio.create_task(env.a.post(f"/api/chats/{per_char_chat['id']}/turn", json={"text": "Tiếp tục"}))
    await asyncio.wait_for(started.wait(), timeout=10)
    assert (await env.a.post(f"/api/chats/{per_char_chat['id']}/stop")).json() == {"stopped": True}
    gate.set()
    resp = await asyncio.wait_for(task, timeout=10)
    stop_events = parse_sse(resp.text)
    notice_codes = {e["code"] for e in stop_events if e["type"] == "notice"}
    assert "scene_parse_failed" not in notice_codes
    assert any(e["type"] == "speaker_end" and e["stopped"] is True for e in stop_events)
