"""Writer reasoning: the chat setting reaches OpenRouter, `reasoning` events stream, and the text is saved in meta."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tests.chat.conftest import ChatEnv, make_character, make_chat, run_turn, script_llm


def reasoning_stream(thoughts: list[str], parts: list[str]) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = [{"id": "g", "choices": [{"delta": {"role": "assistant", "content": ""}}]}]
    chunks += [{"id": "g", "choices": [{"delta": {"reasoning": t}, "finish_reason": None}]} for t in thoughts]
    chunks += [{"id": "g", "choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in parts]
    chunks.append({"id": "g", "choices": [{"delta": {}, "finish_reason": "stop"}]})
    chunks.append({"id": "g", "choices": [], "usage": {"prompt_tokens": 100, "completion_tokens": 40}})
    return {"status": 200, "sse": chunks}


def writer_bodies(env: ChatEnv) -> list[dict[str, Any]]:
    def is_writer(r: httpx.Request) -> bool:
        return r.url.path == "/api/v1/chat/completions" and b'"stream":true' in r.content.replace(b" ", b"")

    return [json.loads(r.content) for r in env.llm.requests if is_writer(r)]


async def test_reasoning_streams_and_is_saved(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    assert chat["settings"]["writer"]["reasoning"] == "medium"
    script_llm(env.llm, character_id, writer=[reasoning_stream(["Mai đang ", "bận."], ["Mai gật đầu."])])

    events = await run_turn(env.a, chat["id"], "Chào Mai")
    kinds = [e["type"] for e in events]
    assert kinds.index("speaker_start") < kinds.index("reasoning") < kinds.index("draft")
    thoughts = [e for e in events if e["type"] == "reasoning"]
    assert "".join(e["delta"] for e in thoughts) == "Mai đang bận." and {e["attempt"] for e in thoughts} == {0}
    # Reasoning never leaks into the visible reply.
    assert "".join(e["delta"] for e in events if e["type"] == "draft") == "Mai gật đầu."

    body = writer_bodies(env)[-1]
    assert body["reasoning"] == {"enabled": True, "effort": "medium"}
    assert body["max_tokens"] > 1500

    rows = (await env.a.get(f"/api/chats/{chat['id']}/messages")).json()
    assert rows[-1]["variants"][0]["content"] == "Mai gật đầu."
    assert rows[-1]["meta"]["reasoning"] == "Mai đang bận."


async def test_reasoning_off_sends_disabled_and_saves_nothing(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    settings = dict(chat["settings"], writer={"reasoning": "off"})
    assert (await env.a.patch(f"/api/chats/{chat['id']}", json={"settings": settings})).status_code == 200
    script_llm(env.llm, character_id, writer=[reasoning_stream([], ["Xin chào."])])

    events = await run_turn(env.a, chat["id"], "Chào")
    assert "reasoning" not in [e["type"] for e in events]
    body = writer_bodies(env)[-1]
    assert body["reasoning"] == {"enabled": False} and body["max_tokens"] == 1500
    rows = (await env.a.get(f"/api/chats/{chat['id']}/messages")).json()
    assert "reasoning" not in rows[-1]["meta"]
