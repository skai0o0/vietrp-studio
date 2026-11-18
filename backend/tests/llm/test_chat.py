from __future__ import annotations

import json

import httpx
import pytest

from app.llm.chat import (
    CHAT_PATH,
    ChatParams,
    ContentDelta,
    Finish,
    ReasoningDelta,
    complete_chat,
    stream_chat,
)
from app.llm.client import LLMError
from app.llm.usage import Usage
from tests.llm.helpers import (
    FAKE_KEY,
    ChunkedStream,
    FakeRecorder,
    Handler,
    load_bytes,
    load_json,
    make_client,
    make_context,
)

MESSAGES = [{"role": "user", "content": "Chào"}]


def sse_handler(chunk_size: int, seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=ChunkedStream(load_bytes("chat_stream.sse"), chunk_size),
        )

    return handler


@pytest.mark.parametrize("chunk_size", [7, 64, 100_000])
async def test_stream_parsing_with_split_chunks(chunk_size: int) -> None:
    seen: list[httpx.Request] = []
    client, _ = make_client(sse_handler(chunk_size, seen))
    recorder = FakeRecorder()
    events = [
        e
        async for e in stream_chat(
            client,
            FAKE_KEY,
            "m/x",
            MESSAGES,
            ChatParams(reasoning="medium", provider={"order": ["A"]}),
            recorder=recorder,
            context=make_context("writer"),
        )
    ]
    await client.aclose()

    text = "".join(e.text for e in events if isinstance(e, ContentDelta))
    assert text == "Xin chào thế giới"
    assert [e.text for e in events if isinstance(e, ReasoningDelta)] == ["Hmm, "]
    assert Finish(reason="length") in events
    usage = events[-1]
    assert isinstance(usage, Usage)
    assert (usage.prompt_tokens, usage.completion_tokens, usage.reasoning_tokens, usage.cost) == (120, 30, 12, 0.0004)

    request = seen[0]
    assert request.url.path == CHAT_PATH
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    assert request.headers["x-title"] == "VietRP Studio"
    body = json.loads(request.content)
    assert body["stream"] is True
    assert body["usage"] == {"include": True}
    assert body["reasoning"] == {"enabled": True, "effort": "medium"}
    assert body["provider"] == {"order": ["A"]}

    assert len(recorder.calls) == 1
    assert recorder.calls[0][2:4] == ("writer", "m/x")


async def test_reasoning_off_and_referer_header() -> None:
    seen: list[httpx.Request] = []
    client, _ = make_client(sse_handler(50, seen), http_referer="https://studio.example")
    _ = [e async for e in stream_chat(client, FAKE_KEY, "m/x", MESSAGES, ChatParams(reasoning="off"))]
    await client.aclose()
    assert json.loads(seen[0].content)["reasoning"] == {"enabled": False}
    assert seen[0].headers["http-referer"] == "https://studio.example"


async def test_stream_error_chunk_raises_without_key() -> None:
    body = b'data: {"error":{"message":"boom ' + FAKE_KEY.encode() + b'","code":500}}\n\n'
    client, _ = make_client(lambda r: httpx.Response(200, content=body))
    with pytest.raises(LLMError) as info:
        _ = [e async for e in stream_chat(client, FAKE_KEY, "m/x", MESSAGES)]
    await client.aclose()
    assert info.value.code == "llm_stream_error"
    assert FAKE_KEY not in str(info.value)


async def test_complete_chat_records_once() -> None:
    client, _ = make_client(lambda r: httpx.Response(200, json=load_json("chat_complete.json")))
    recorder = FakeRecorder()
    text, usage = await complete_chat(
        client, FAKE_KEY, "m/x", MESSAGES, recorder=recorder, context=make_context("archivist")
    )
    await client.aclose()
    assert text == "Đã rõ."
    assert usage.prompt_tokens == 50 and usage.cost == 0.0001
    assert len(recorder.calls) == 1


async def test_recorder_without_context_is_rejected() -> None:
    client, _ = make_client(lambda r: httpx.Response(200, json=load_json("chat_complete.json")))
    with pytest.raises(ValueError):
        await complete_chat(client, FAKE_KEY, "m/x", MESSAGES, recorder=FakeRecorder())
    await client.aclose()
