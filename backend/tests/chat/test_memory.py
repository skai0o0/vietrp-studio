"""Memory pipeline, token calibration, snapshot repository, and `POST /api/chats/{id}/summarize` tests."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest

from app.core.deps import get_gateway_factory
from app.llm.defaults import DEFAULT_MODELS
from app.llm.fake import _Fixture
from app.services.chat_service import get_unit_of_work, parse_chat_id
from app.services.turn_service import ensure_openrouter_key, get_key_check
from tests.chat.conftest import (
    COMPLETIONS,
    DECISIONS,
    DIRECTOR_PASS,
    ChatEnv,
    decision,
    make_character,
    make_chat,
    make_persona,
    run_turn,
    script_llm,
    sse_stream,
)
from tests.chat.test_world_chat import make_world, make_world_chat
from tests.chat.test_world_turn import _script_world_llm


def _archivist_response(summary: str, events: list[tuple[str, str]]) -> dict[str, Any]:
    lines = ["TÓM TẮT:", summary, "", "SỰ KIỆN ĐÁNG NHỚ:"]
    if events:
        lines.extend(f"- {title} | {content}" for title, content in events)
    else:
        lines.append("(chưa có)")
    return {
        "status": 200,
        "json": {
            "choices": [{"message": {"role": "assistant", "content": "\n".join(lines)}}],
            "usage": {"prompt_tokens": 180, "completion_tokens": 55, "cost": 0.0002},
        },
    }


def _bond_completion(pairs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "status": 200,
        "json": {
            "choices": [{"message": {"role": "assistant", "content": json.dumps({"pairs": pairs})}}],
            "usage": {"prompt_tokens": 90, "completion_tokens": 35, "cost": 0.0001},
        },
    }


async def _vault_id(client: httpx.AsyncClient) -> uuid.UUID:
    resp = await client.get("/api/vault/me")
    assert resp.status_code == 200
    return uuid.UUID(resp.json()["vault"]["id"])


async def test_memory_snapshot_repository_crud_ordering_and_vault_isolation(env: ChatEnv) -> None:
    char_id = await make_character(env.a, name="Mai", age=22)
    chat = await make_chat(env.a, char_id)
    chat_uuid = parse_chat_id(chat["id"])
    vault_a = await _vault_id(env.a)
    vault_b = await _vault_id(env.b)
    uow = env.app.dependency_overrides[get_unit_of_work]()

    async with uow() as r:
        await r.messages.add_snapshot(
            vault_a, chat_uuid, upto_seq=10, summary="S10 first", events=[{"id": "sk_1", "title": "A", "content": "B"}]
        )
        await r.messages.add_snapshot(vault_a, chat_uuid, upto_seq=4, summary="S4", events=[])
        await r.messages.add_snapshot(vault_a, chat_uuid, upto_seq=10, summary="S10 second", events=[])
        await r.commit()

    async with uow() as r:
        snaps_a = await r.messages.list_snapshots(vault_a, chat_uuid)
        snaps_b = await r.messages.list_snapshots(vault_b, chat_uuid)
        assert [(s.upto_seq, s.summary) for s in snaps_a] == [(4, "S4"), (10, "S10 first"), (10, "S10 second")]
        assert snaps_b == []

        before_nine = await r.messages.latest_snapshot_at_or_before(vault_a, chat_uuid, 9)
        assert before_nine is not None and before_nine.upto_seq == 4
        at_ten = await r.messages.latest_snapshot_at_or_before(vault_a, chat_uuid, 10)
        assert at_ten is not None and at_ten.summary == "S10 second"
        assert await r.messages.latest_snapshot_at_or_before(vault_b, chat_uuid, 10) is None
        assert await r.messages.latest_snapshot_at_or_before(vault_a, chat_uuid, 3) is None

        assert await r.messages.delete_snapshots_after(vault_b, chat_uuid, 0) == 0
        assert await r.messages.delete_snapshots_after(vault_a, chat_uuid, 4) == 2
        await r.commit()

    async with uow() as r:
        remaining = await r.messages.list_snapshots(vault_a, chat_uuid)
        assert [(s.upto_seq, s.summary) for s in remaining] == [(4, "S4")]


async def test_correction_table_calibration_from_writer_usage(env: ChatEnv) -> None:
    char_id = await make_character(env.a, name="Mai", age=22)
    chat = await make_chat(env.a, char_id)
    writer_model = DEFAULT_MODELS["writer"]
    corrections = env.app.state.llm_services.corrections
    assert corrections.factor(writer_model) == 1.0

    before = (await env.a.get(f"/api/chats/{chat['id']}/prompt-preview", params={"text": "Xin chào Mai"})).json()
    script_llm(env.llm, char_id, writer=[sse_stream("Chào cậu.", prompt_tokens=4000)])
    await run_turn(env.a, chat["id"], "Xin chào Mai")

    calibrated_factor = corrections.factor(writer_model)
    assert calibrated_factor > 1.2
    after = (await env.a.get(f"/api/chats/{chat['id']}/prompt-preview", params={"text": "Xin chào Mai"})).json()
    assert after["total_tokens"] > before["total_tokens"]


async def test_auto_archivist_single_chat_snapshot_and_bond_refresh(env: ChatEnv) -> None:
    char_id = await make_character(
        env.a,
        name="Mai",
        age=22,
        addressing={"user": "tôi - cậu"},
        greetings=["Mai vẫy tay chào {{user}}."],
    )
    persona_id = await make_persona(env.a, name="Nam")
    chat = await make_chat(
        env.a,
        char_id,
        persona_id=persona_id,
        settings={"memory": {"context_length": 2500, "summarize_at": 0.5}},
    )
    pair = f"{char_id}:user"

    # Script initial bonds -> turn 1..4 -> auto Archivist -> refreshed bonds.
    env.llm.add(
        [
            _bond_completion(
                {
                    pair: [
                        {"addressing": "tôi - cậu", "relationship": "đồng nghiệp", "stance": "lịch sự", "closeness": 1}
                    ]
                }
            ),
            _bond_completion(
                {
                    pair: [
                        {
                            "addressing": "anh - em (bị ghim)",
                            "nickname": "Nam còi",
                            "relationship": "đồng đội thân thiết",
                            "stance": "bị chặn bởi manual",
                            "closeness": 3,
                            "history": "Đã cùng cứu dự án quan trọng.",
                        }
                    ]
                }
            ),
        ],
        {"path": COMPLETIONS, "stream": False, "contains": "Mã cặp"},
        name="single_bonds",
    )
    env.llm.add(
        [decision({"bond__0": {"choice": "1", "confidence": 0.9, "probabilities": {"1": 0.9}}})],
        {"path": DECISIONS, "contains": "bond__0"},
        name="single_bond_selector",
    )
    env.llm.add(
        [
            decision(
                {
                    "turn_type": {"choice": "dialogue", "confidence": 0.9, "probabilities": {"dialogue": 0.9}},
                    "speaker": {"choice": "character", "confidence": 0.9, "probabilities": {"character": 0.9}},
                    "addressee": {"choice": "character", "confidence": 0.9, "probabilities": {"character": 0.9}},
                }
            )
        ],
        {"path": DECISIONS, "contains": "turn_type"},
        name="single_orchestrator",
    )
    high_prio_director = decision(
        {
            "answers_last": {"noul": 0.95},
            "no_new_events": {"noul": 0.05},
            "no_player_voice": {"noul": 0.03},
            "no_assistant_voice": {"noul": 0.02},
            "user_led": {"noul": 0.1},
            "priority": {"score": 2.0},
        }
    )
    env.llm.add([high_prio_director, DIRECTOR_PASS], {"path": DECISIONS, "contains": "answers_last"}, name="director")
    env.llm.add(
        [
            _archivist_response(
                "- Mai và Nam hợp tác điều tra sự cố máy chủ.",
                [("Mai hứa giúp Nam", "Mai hứa cùng Nam khôi phục dữ liệu vào tối nay.")],
            )
        ],
        {"path": COMPLETIONS, "stream": False, "contains": "archivist"},
        name="single_archivist",
    )
    env.llm.add(
        [sse_stream("Mai gật đầu đồng ý.", prompt_tokens=600)], {"path": COMPLETIONS, "stream": True}, name="writer"
    )

    # Turn 1 creates initial bonds; hand-edit `stance` so `manual` protects it from refresh.
    t1 = await run_turn(env.a, chat["id"], "Lượt một: cùng kiểm tra phòng máy nhé?")
    assert "archivist" not in [e["type"] for e in t1]

    bonds_now = (await env.a.get(f"/api/chats/{chat['id']}")).json()["state"]["bonds"]
    edited = json.loads(json.dumps(bonds_now[pair]))
    edited["fields"]["stance"] = "tin tưởng tuyệt đối"
    patch_resp = await env.a.patch(f"/api/chats/{chat['id']}/state", json={"bonds": {pair: edited}})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["state"]["bonds"][pair]["manual"] == ["stance"]

    # Turns 2..3 stay below 50% of 2500; turn 4 reaches > 6 unsummarized AND >= 1250 tokens.
    long_line = "Nam kể chi tiết từng đầu mối vừa tìm thấy trong hồ sơ lưu trữ cũ kỹ. " * 38
    await run_turn(env.a, chat["id"], "Lượt hai: tìm thấy manh mối mới.")
    await run_turn(env.a, chat["id"], "Lượt ba: mở khóa phòng lưu trữ.")
    t4 = await run_turn(env.a, chat["id"], f"Lượt bốn: {long_line}")

    kinds = [e["type"] for e in t4]
    assert "archivist" in kinds and "bonds" in kinds
    assert kinds.index("speaker_end") < kinds.index("archivist") < kinds.index("bonds") < kinds.index("done")

    arch_ev = next(e for e in t4 if e["type"] == "archivist")
    assert arch_ev["events_added"] == 1
    assert "Mai và Nam hợp tác" in arch_ev["summary"]

    # Archivist prompt marked priority=2 turns with [QUAN TRỌNG].
    arch_reqs = [
        r
        for r in env.llm.requests_to(COMPLETIONS)
        if b'"stream":false' in r.content.replace(b" ", b"") and b"archivist" in r.content
    ]
    assert len(arch_reqs) == 1
    arch_prompt = json.loads(arch_reqs[0].content)["messages"][1]["content"]
    assert "[QUAN TRỌNG] Mai:" in arch_prompt

    # Persisted chat state + snapshot + bond preservation
    detail = (await env.a.get(f"/api/chats/{chat['id']}")).json()
    assert detail["state"]["summary_upto"] == 3  # 9 messages total -> kept 6 newest (seq 3..8)
    assert len(detail["state"]["events"]) == 1
    refreshed_bond = detail["state"]["bonds"][pair]
    assert refreshed_bond["fields"]["addressing"] == "tôi - cậu"  # card pin preserved
    assert refreshed_bond["fields"]["stance"] == "tin tưởng tuyệt đối"  # manual edit preserved
    assert refreshed_bond["fields"]["relationship"] == "đồng đội thân thiết"  # refreshed!
    assert refreshed_bond["fields"]["closeness"] == 3
    assert refreshed_bond["changes"][-1]["seq"] == 8  # latest message seq

    vault_id = await _vault_id(env.a)
    uow = env.app.dependency_overrides[get_unit_of_work]()
    async with uow() as r:
        snaps = await r.messages.list_snapshots(vault_id, parse_chat_id(chat["id"]))
    assert len(snaps) == 1
    assert snaps[0].upto_seq == 3
    assert snaps[0].events[0]["id"] == "sk_mai_hua_giup_nam"

    # Prompt preview replaces seq 0..2 with memory layer (summary + events).
    preview = (await env.a.get(f"/api/chats/{chat['id']}/prompt-preview", params={"text": "Tiếp tục"})).json()
    layer_map = {la["name"]: la["text"] for la in preview["layers"]}
    assert "memory" in layer_map
    assert "Mai và Nam hợp tác" in layer_map["memory"]
    assert "Mai hứa giúp Nam: Mai hứa cùng Nam khôi phục dữ liệu vào tối nay." in layer_map["memory"]
    assert "Mai vẫy tay chào" not in layer_map.get("history", "")
    assert "Lượt hai:" in layer_map.get("history", "")


async def test_auto_archivist_world_chat_and_non_critical_failure_notice(env: ChatEnv) -> None:
    vy_id = await make_character(
        env.a,
        name="Trần Hạ Vy",
        age=20,
        addressing={"user": "tôi - cậu", "by_character": {"han": "mày - tao"}},
    )
    han_id = await make_character(env.a, name="Nguyễn Gia Hân", age=21)
    world_id = await make_world(env.a)
    persona_id = await make_persona(env.a, name="Nam")
    chat = await make_world_chat(
        env.a,
        world_id,
        "gio_ra_choi",
        [vy_id, han_id],
        persona_id=persona_id,
        settings={"memory": {"context_length": 2500, "summarize_at": 0.5}},
    )

    initial_bonds = {
        "vy:user": [{"addressing": "tôi - cậu", "relationship": "bạn học", "stance": "vui vẻ", "closeness": 1}],
        "han:user": [{"addressing": "tôi - cậu", "relationship": "quen biết", "stance": "điềm tĩnh", "closeness": 1}],
        "vy:han": [{"addressing": "mày - tao", "relationship": "bạn cùng lớp", "stance": "thoải mái", "closeness": 2}],
        "han:vy": [{"addressing": "tôi - bà", "relationship": "bạn cùng lớp", "stance": "ôn hòa", "closeness": 2}],
    }
    updated_bonds = {
        "vy:user": [
            {"addressing": "override-ignored", "relationship": "đồng minh", "stance": "tin cậy", "closeness": 3}
        ],
        "han:user": [{"addressing": "tôi - cậu", "relationship": "bạn thân", "stance": "ấm áp", "closeness": 3}],
        "vy:han": [
            {"addressing": "override-ignored", "relationship": "bạn chí cốt", "stance": "gắn bó", "closeness": 4}
        ],
        "han:vy": [{"addressing": "bà - tui", "relationship": "bạn chí cốt", "stance": "tin cậy", "closeness": 4}],
    }
    _script_world_llm(
        env.llm,
        orchestrator_answers={
            "turn_type": {"choice": "dialogue", "confidence": 0.9, "probabilities": {"dialogue": 0.9}},
            "speaker": {"choice": "vy", "confidence": 0.9, "probabilities": {"vy": 0.9}},
            "addressee": {"choice": "vy", "confidence": 0.85, "probabilities": {"vy": 0.85}},
            "followup__han": {"noul": 0.1},
        },
        writer=[sse_stream("Vy trả lời ngắn gọn.", prompt_tokens=700)],
    )
    # Replace scripted world_bond_drafter with 2-step sequence (initial + refreshed).
    env.llm._fixtures = [f for f in env.llm._fixtures if f.name != "world_bond_drafter"]
    env.llm._fixtures.insert(
        0,
        _Fixture(
            "world_bond_drafter",
            {"path": COMPLETIONS, "stream": False, "contains": "vy:user"},
            [_bond_completion(initial_bonds), _bond_completion(updated_bonds)],
        ),
    )
    env.llm._fixtures.insert(
        0,
        _Fixture(
            "world_archivist",
            {"path": COMPLETIONS, "stream": False, "contains": "archivist"},
            [
                _archivist_response(
                    "- Cả nhóm bàn kế hoạch ở căn tin.",
                    [("Vy và Hân lập nhóm", "Vy và Hân quyết định hợp tác tìm chiếc sổ bị mất.")],
                ),
                {"status": 400, "json": {"error": {"message": "archivist down"}}},
            ],
        ),
    )

    long_msg = "Mọi người bàn bạc rất kỹ về manh mối mới vừa xuất hiện ở sân trường. " * 32
    await run_turn(env.a, chat["id"], "Tin 1 ngắn.")
    await run_turn(env.a, chat["id"], "Tin 2 ngắn.")
    await run_turn(env.a, chat["id"], "Tin 3 ngắn.")
    ev = await run_turn(env.a, chat["id"], f"Tin 4: {long_msg}")  # 9 messages -> > 6 kept, >= 50% of 2400

    kinds = [e["type"] for e in ev]
    assert "state" in kinds and "archivist" in kinds and "bonds" in kinds
    assert kinds.index("state") < kinds.index("archivist") < kinds.index("bonds") < kinds.index("done")

    detail = (await env.a.get(f"/api/chats/{chat['id']}")).json()
    assert detail["state"]["summary_upto"] == 3
    assert detail["state"]["bonds"]["vy:han"]["fields"]["addressing"] == "mày - tao"  # pin intact
    assert detail["state"]["bonds"]["vy:han"]["fields"]["relationship"] == "bạn chí cốt"  # updated

    # Next turn has > 6 unsummarized messages (seq 3..10) and Archivist fails -> `archivist_failed` notice.
    ev_fail = await run_turn(env.a, chat["id"], f"Tin 5: {long_msg}")
    assert any(e["type"] == "notice" and e["code"] == "archivist_failed" for e in ev_fail)
    assert ev_fail[-1]["type"] == "done"


async def test_manual_summarize_endpoint_and_error_cases(env: ChatEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    char_id = await make_character(env.a, name="Mai", age=22, greetings=["Mai chào {{user}}."])
    persona_id = await make_persona(env.a, name="Nam")
    chat = await make_chat(env.a, char_id, persona_id=persona_id)

    script_llm(env.llm, char_id, writer=[sse_stream("Mai cười.")])
    env.llm.add(
        [
            _archivist_response(
                "- Hai bạn làm quen với nhau.",
                [("Mai tặng Nam thẻ thư viện", "Mai đưa Nam thẻ thư viện dự phòng.")],
            ),
            _archivist_response(
                "- Hai bạn hẹn mai gặp lại.",
                [("Mai tặng Nam thẻ thư viện", "Mai đưa Nam thẻ thư viện dự phòng.")],
            ),
        ],
        {"path": COMPLETIONS, "stream": False, "contains": "archivist"},
        name="manual_archivist",
    )

    await run_turn(env.a, chat["id"], "Chào Mai")
    await run_turn(env.a, chat["id"], "Cậu khỏe không?")  # seq 0..4 (5 messages)

    # Vault B isolation -> 404
    stolen = await env.b.post(f"/api/chats/{chat['id']}/summarize")
    assert stolen.status_code == 404 and stolen.json()["error"]["code"] == "chat_not_found"

    # First summarize: > 2 unsummarized -> keeps 2 newest (seq 3, 4), compresses seq 0..2 -> summary_upto=3
    res1 = await env.a.post(f"/api/chats/{chat['id']}/summarize")
    assert res1.status_code == 200, res1.text
    out1 = res1.json()
    assert out1["state"]["summary_upto"] == 3
    assert "Hai bạn làm quen" in out1["state"]["summary"]
    assert len(out1["state"]["events"]) == 1

    preview = (await env.a.get(f"/api/chats/{chat['id']}/prompt-preview")).json()
    layer_map = {la["name"]: la["text"] for la in preview["layers"]}
    assert "Hai bạn làm quen" in layer_map["memory"]
    assert "Mai tặng Nam thẻ thư viện: Mai đưa Nam thẻ thư viện dự phòng." in layer_map["memory"]
    assert "Mai chào Nam" not in layer_map.get("history", "")
    assert "Cậu khỏe không?" in layer_map.get("history", "")

    # Second summarize: 2 unsummarized remaining -> compresses both -> summary_upto=5
    res2 = await env.a.post(f"/api/chats/{chat['id']}/summarize")
    assert res2.status_code == 200, res2.text
    assert res2.json()["state"]["summary_upto"] == 5

    vault_id = await _vault_id(env.a)
    uow = env.app.dependency_overrides[get_unit_of_work]()
    async with uow() as r:
        snaps = await r.messages.list_snapshots(vault_id, parse_chat_id(chat["id"]))
    assert [s.upto_seq for s in snaps] == [3, 5]

    # Third summarize: 0 unsummarized -> 422 nothing_to_summarize
    empty_res = await env.a.post(f"/api/chats/{chat['id']}/summarize")
    assert empty_res.status_code == 422 and empty_res.json()["error"]["code"] == "nothing_to_summarize"

    # Missing OpenRouter key -> 400 openrouter_key_missing (without swallowing via run_non_critical)
    chat_no_key = await make_chat(env.a, char_id)

    async def _no_secret(*_args: Any, **_kwargs: Any) -> str | None:
        return None

    monkeypatch.setattr("app.services.vault_service.get_secret", _no_secret)
    prev_key_check = env.app.dependency_overrides.pop(get_key_check, None)
    prev_gw = env.app.dependency_overrides.pop(get_gateway_factory, None)
    try:
        # Ensure real `ensure_openrouter_key` checks vault without hitting an unconfigured DB in fake mode.
        def _fake_session_ctx() -> Any:
            class _Dummy:
                async def __aenter__(self) -> object:
                    return object()

                async def __aexit__(self, *_a: object) -> None:
                    return None

            return _Dummy()

        monkeypatch.setattr("app.core.deps.get_sessionmaker", lambda: _fake_session_ctx)
        assert ensure_openrouter_key is not None
        no_key_res = await env.a.post(f"/api/chats/{chat_no_key['id']}/summarize")
        assert no_key_res.status_code == 400 and no_key_res.json()["error"]["code"] == "openrouter_key_missing"
    finally:
        if prev_key_check is not None:
            env.app.dependency_overrides[get_key_check] = prev_key_check
        if prev_gw is not None:
            env.app.dependency_overrides[get_gateway_factory] = prev_gw
