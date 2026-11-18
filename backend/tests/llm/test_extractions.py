from __future__ import annotations

import json

import httpx
import pytest

from app.llm.decisions import QuestionBudgetExceeded
from app.llm.extractions import (
    ChatFallbackExtractionClient,
    Field,
    OpenRouterExtractionClient,
    ResilientExtractionClient,
)
from tests.llm.helpers import FAKE_KEY, FakeRecorder, load_json, make_client, make_context

FIELDS = {"time": Field(instructions="Thời gian hiện tại trong truyện")}


async def test_primary_returns_value_and_confidence() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=load_json("extractions_ok.json"))

    client, _ = make_client(handler)
    recorder = FakeRecorder()
    result = await OpenRouterExtractionClient(client).extract(
        FAKE_KEY, "m/decision", "Chiều thứ Bảy, họ gặp nhau.", FIELDS, recorder=recorder, context=make_context()
    )
    await client.aclose()
    assert result.values["time"].value == "Chiều thứ Bảy"
    assert result.values["time"].confidence == 0.9
    assert len(recorder.calls) == 1
    assert seen[0].url.path == "/api/alpha/extractions"
    body = json.loads(seen[0].content)
    assert body["state"] == "Chiều thứ Bảy, họ gặp nhau."
    assert body["fields"]["time"] == {"type": "text", "instructions": "Thời gian hiện tại trong truyện"}


async def test_fallback_on_410_uses_chat_json() -> None:
    reply = {
        "choices": [{"message": {"content": '{"time": {"value": "Tối", "confidence": 1.4}}'}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "cost": 0.00002},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/alpha/extractions":
            return httpx.Response(410, text="gone")
        return httpx.Response(200, json=reply)

    client, _ = make_client(handler)
    recorder = FakeRecorder()
    resilient = ResilientExtractionClient(OpenRouterExtractionClient(client), ChatFallbackExtractionClient(client))
    result = await resilient.extract(FAKE_KEY, "m/decision", "text", FIELDS, recorder=recorder, context=make_context())
    await client.aclose()
    assert result.used_fallback is True
    assert result.values["time"].value == "Tối"
    assert result.values["time"].confidence == 1.0  # clamped
    assert len(recorder.calls) == 1


async def test_budget_applies_to_fields() -> None:
    client, _ = make_client(lambda r: httpx.Response(500), max_questions=0)
    with pytest.raises(QuestionBudgetExceeded):
        await OpenRouterExtractionClient(client).extract(FAKE_KEY, "m/decision", "x", FIELDS)
    await client.aclose()


async def test_null_value_becomes_empty_string() -> None:
    body = {"answers": {"time": {"value": None, "confidence": 0.1}}}
    client, _ = make_client(lambda r: httpx.Response(200, json=body))
    result = await OpenRouterExtractionClient(client).extract(FAKE_KEY, "m/decision", "x", FIELDS)
    await client.aclose()
    assert result.values["time"].value == ""
