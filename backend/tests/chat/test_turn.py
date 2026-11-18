"""Full single-chat turns over RecordedLLM: event order, persistence, Director modes, stop and concurrency."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.fake import _Fixture
from app.services.chat_service import get_unit_of_work, parse_chat_id
from tests.chat.conftest import (
    DECISIONS,
    DIRECTOR_PASS,
    ChatEnv,
    director_fail,
    make_character,
    make_chat,
    make_persona,
    parse_sse,
    run_turn,
    script_llm,
    sse_stream,
)


def types(events: list[dict[str, Any]]) -> list[str]:
    return [e["type"] for e in events]


def text_of(events: list[dict[str, Any]], kind: str) -> str:
    return "".join(e["delta"] for e in events if e["type"] == kind)


async def messages(env: ChatEnv, chat_id: str, suffix: str = "") -> list[dict[str, Any]]:
    response = await env.a.get(f"/api/chats/{chat_id}/messages{suffix}")
    assert response.status_code == 200
    result: list[dict[str, Any]] = response.json()
    return result


def is_writer_request(request: httpx.Request) -> bool:
    return request.url.path == "/api/v1/chat/completions" and b'"stream":true' in request.content.replace(b" ", b"")


async def test_full_turn_events_persistence_and_state_before(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    persona_id = await make_persona(env.a)
    chat = await make_chat(env.a, character_id, persona_id=persona_id)
    assert chat["settings"]["director"]["stream_mode"] == "draft_then_replace"
    script_llm(env.llm, character_id, writer=[sse_stream("Mai mỉm cười.", " Chào cậu.")])

    events = await run_turn(env.a, chat["id"], "Chào Mai")
    kinds = types(events)
    # Bonds first, then the plan, then the speaker with draft deltas, the verdict and done.
    assert kinds.index("bonds") < kinds.index("plan") < kinds.index("speaker_start") < kinds.index("draft")
    assert kinds.index("draft") < kinds.index("director") < kinds.index("speaker_end") < kinds.index("done")
    assert text_of(events, "draft") == "Mai mỉm cười. Chào cậu."
    assert "reset_content" not in kinds
    assert {e["agent"] for e in events if e["type"] == "usage"} >= {"orchestrator", "writer", "director"}
    assert all("type" in e for e in events)
    director_event = next(e for e in events if e["type"] == "director")
    assert director_event["passed"] is True and len(director_event["criteria"]) == 4

    rows = await messages(env, chat["id"])
    assert [(m["seq"], m["speaker"]) for m in rows] == [(0, character_id), (1, "user"), (2, character_id)]
    assert rows[0]["variants"][0]["content"].startswith("Chào Nam")  # {{user}} replaced by the persona name
    ai = rows[2]
    assert ai["variants"][0]["content"] == "Mai mỉm cười. Chào cậu."
    assert ai["variants"][0]["director"]["passed"] is True
    assert ai["meta"]["usage"]["prompt_tokens"] > 0 and ai["meta"]["priority"] == 1
    assert events[-1]["message_ids"] == [rows[1]["id"], rows[2]["id"]]

    detail = (await env.a.get(f"/api/chats/{chat['id']}")).json()
    bonds = detail["state"]["bonds"][f"{character_id}:user"]
    assert bonds["fields"]["relationship"] == "đồng nghiệp" and detail["messages_count"] == 3
    assert next(e for e in events if e["type"] == "bonds")["bonds"] == detail["state"]["bonds"]

    # The second turn does not draft bonds again.
    before = len(env.llm.requests)
    again = await run_turn(env.a, chat["id"], "Hôm nay quán đông không?")
    assert "bonds" not in types(again)
    assert not any("Mã cặp".encode() in r.content for r in env.llm.requests[before:])


async def test_state_before_values(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(env.llm, character_id, writer=[sse_stream("Xin chào.")])
    await run_turn(env.a, chat["id"], "Chào")
    # The API does not expose state_before; read it through the unit of work.
    vault_id = uuid.UUID((await env.a.get("/api/vault/me")).json()["vault"]["id"])
    uow = env.app.dependency_overrides[get_unit_of_work]()
    async with uow() as r:
        rows = await r.messages.page(vault_id, parse_chat_id(chat["id"]), before=None, limit=10)
    assert [m.seq for m in rows] == [0, 1, 2]
    expected_initial = {"bonds": {}, "summary": "", "summary_upto": 0, "events": []}
    assert rows[0].state_before == expected_initial and rows[1].state_before == expected_initial
    assert f"{character_id}:user" in (rows[2].state_before or {})["bonds"]


async def test_draft_then_replace_rejection_replaces_the_draft(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(
        env.llm,
        character_id,
        writer=[sse_stream("Bản nháp lỗi."), sse_stream("Bản sửa tốt.")],
        director=[director_fail(), DIRECTOR_PASS],
    )
    events = await run_turn(env.a, chat["id"], "Chào")
    kinds = types(events)
    assert kinds.count("director") == 2 and kinds.count("rejudge") == 1
    first_verdict = next(e for e in events if e["type"] == "director")
    assert first_verdict["passed"] is False
    assert any(c["hint_vi"] for c in first_verdict["criteria"] if not c["passed"])
    assert kinds.index("reset_content") > kinds.index("director")
    assert kinds.index("rejudge") > kinds.index("reset_content")
    assert [e["delta"] for e in events if e["type"] == "draft"] == ["Bản nháp lỗi.", "Bản sửa tốt."]
    # The retry request carries the Director's hints as a user message (never a system layer).
    writer_requests = [r for r in env.llm.requests if is_writer_request(r)]
    assert len(writer_requests) == 2 and "Chỉ dẫn sửa".encode() in writer_requests[1].content
    ai = (await messages(env, chat["id"], "?include=drafts"))[-1]
    variant = ai["variants"][0]
    assert variant["content"] == "Bản sửa tốt." and variant["draft"] == "Bản nháp lỗi."
    assert ai["meta"]["attempts"] == 2


async def test_retries_exhausted_keeps_the_higher_scoring_variant(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(
        env.llm,
        character_id,
        writer=[sse_stream("Tốt nhất."), sse_stream("Tệ hơn."), sse_stream("Tệ nhất.")],
        director=[director_fail(0.5), director_fail(0.7), director_fail(0.9)],
    )
    events = await run_turn(env.a, chat["id"], "Chào")
    assert types(events).count("director") == 3 and types(events).count("rejudge") == 2
    # The client holds the third draft, but the first scored higher, so the buffer is replaced at the end.
    end = types(events).index("speaker_end")
    assert [e["type"] for e in events[end - 2 : end]] == ["reset_content", "content"]
    assert events[end - 1]["delta"] == "Tốt nhất."
    assert (await messages(env, chat["id"]))[-1]["variants"][0]["content"] == "Tốt nhất."


async def test_hold_until_approved_sends_no_draft(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id, settings={"director": {"stream_mode": "hold_until_approved"}})
    script_llm(
        env.llm,
        character_id,
        writer=[sse_stream("Nháp một."), sse_stream("Bản duyệt.")],
        director=[director_fail(), DIRECTOR_PASS],
    )
    events = await run_turn(env.a, chat["id"], "Chào")
    kinds = types(events)
    assert "draft" not in kinds and "reset_content" not in kinds
    assert kinds.count("director") == 2 and kinds.count("rejudge") == 1
    # Only the approved text is sent, once, after the last verdict.
    assert [e["delta"] for e in events if e["type"] == "content"] == ["Bản duyệt."]
    assert kinds.index("content") > max(i for i, k in enumerate(kinds) if k == "director")


async def test_director_disabled_streams_content_directly(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id, settings={"director": {"enabled": False}})
    script_llm(env.llm, character_id, writer=[sse_stream("Một.", " Hai.")])
    events = await run_turn(env.a, chat["id"], "Chào")
    assert text_of(events, "content") == "Một. Hai." and "draft" not in types(events)
    assert "director" not in types(events)


async def test_director_failure_keeps_the_draft_with_a_notice(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(env.llm, character_id, writer=[sse_stream("Giữ lại.")], director=[{"status": 400, "json": {}}])
    events = await run_turn(env.a, chat["id"], "Chào")
    assert any(e["type"] == "notice" and e["code"] == "director_failed" for e in events)
    assert (await messages(env, chat["id"]))[-1]["variants"][0]["content"] == "Giữ lại."


async def test_orchestrator_failure_falls_back_to_narrator(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(env.llm, character_id, writer=[sse_stream("Trời tối dần.")])
    # A failing orchestrator fixture placed first wins the match.
    env.llm._fixtures.insert(
        0, _Fixture("orchestrator_down", {"path": DECISIONS, "contains": "turn_type"}, [{"status": 400, "json": {}}])
    )
    events = await run_turn(env.a, chat["id"], "Chào")
    assert any(e["type"] == "notice" and e["code"] == "orchestrator_fallback" for e in events)
    assert next(e for e in events if e["type"] == "plan")["speakers"][0]["kind"] == "narrator"
    assert (await messages(env, chat["id"]))[-1]["speaker"] == "narrator"


async def test_unsupported_command_and_force(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(env.llm, character_id, writer=[sse_stream("Dạ.")])
    events = await run_turn(env.a, chat["id"], "/time 8h sáng")
    assert types(events) == ["notice", "done"] and events[0]["code"] == "command_unsupported"
    assert len(await messages(env, chat["id"])) == 1  # only the greeting

    forced = await run_turn(env.a, chat["id"], "/force @narrator Cảnh mưa")
    assert next(e for e in forced if e["type"] == "plan")["speakers"][0]["kind"] == "narrator"
    unknown = await run_turn(env.a, chat["id"], "/force @ai_do Cảnh mưa")
    assert any(e["type"] == "notice" and e["code"] == "force_target_unknown" for e in unknown)


class GatedBody(httpx.AsyncByteStream):
    """First half of a stream right away, the rest only once `gate` opens."""

    def __init__(self, first: bytes, second: bytes, gate: asyncio.Event, started: asyncio.Event) -> None:
        self._parts = (first, second)
        self._gate = gate
        self._started = started

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._parts[0]
        self._started.set()
        await self._gate.wait()
        yield self._parts[1]


def sse_chunk(text: str) -> bytes:
    payload = json.dumps({"id": "g", "choices": [{"delta": {"content": text}, "finish_reason": None}]})
    return f"data: {payload}\n\n".encode()


async def test_stop_saves_a_stopped_variant_and_concurrent_turn_gets_409(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(env.llm, character_id, writer=[sse_stream("unused")])
    gate, started = asyncio.Event(), asyncio.Event()
    inner = env.llm

    def handler(request: httpx.Request) -> httpx.Response:
        if is_writer_request(request):
            second = sse_chunk(" Phần sau.") + b"data: [DONE]\n\n"
            body = GatedBody(sse_chunk("Phần đầu."), second, gate, started)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=body)
        return inner._handle(request)

    env.set_transport(httpx.MockTransport(handler))
    task = asyncio.create_task(env.a.post(f"/api/chats/{chat['id']}/turn", json={"text": "Chào"}))
    await asyncio.wait_for(started.wait(), timeout=10)
    second_try = await env.a.post(f"/api/chats/{chat['id']}/turn", json={"text": "Lại"})
    assert second_try.status_code == 409 and second_try.json()["error"]["code"] == "turn_running"
    assert (await env.a.post(f"/api/chats/{chat['id']}/stop")).json() == {"stopped": True}
    gate.set()
    response = await asyncio.wait_for(task, timeout=10)
    events = parse_sse(response.text)
    end = next(e for e in events if e["type"] == "speaker_end")
    assert end["stopped"] is True and events[-1]["type"] == "done"
    ai = (await messages(env, chat["id"]))[-1]
    assert ai["variants"][0]["stopped"] is True and ai["variants"][0]["content"] == "Phần đầu."
    assert (await env.a.post(f"/api/chats/{chat['id']}/stop")).json() == {"stopped": False}
