from __future__ import annotations

import json

import httpx
import pytest

from app.llm.client import LLMError
from app.llm.decisions import (
    ChatFallbackDecisionClient,
    Choice,
    DecisionResult,
    Noul,
    OpenRouterDecisionClient,
    Question,
    QuestionBudgetExceeded,
    ResilientDecisionClient,
    Score,
)
from tests.llm.helpers import FAKE_KEY, FakeRecorder, load_json, make_client, make_context

STATE = {"scene": "Quán cà phê buổi chiều"}
QUESTIONS: dict[str, Question] = {
    "speaker": Choice(criteria={"mai": "Mai", "narrator": "Người dẫn truyện"}, instructions="Ai nói tiếp?"),
    "lore__a": Noul(instructions="Có cần thông tin A không?"),
    "tension": Score(criteria=["Thoải mái", "Bình thường", "Căng"], instructions="Độ căng?"),
}


def route(requests: list[httpx.Request]):  # type: ignore[no-untyped-def]
    """Alpha endpoints answer from fixtures; the chat endpoint answers the fallback fixture."""

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/alpha/decisions":
            return httpx.Response(200, json=load_json("decisions_ok.json"))
        return httpx.Response(200, json=load_json("fallback_decisions_chat.json"))

    return handler


async def test_primary_normalizes_choice_noul_score() -> None:
    requests: list[httpx.Request] = []
    client, _ = make_client(route(requests))
    recorder = FakeRecorder()
    result = await OpenRouterDecisionClient(client).decide(
        FAKE_KEY, "microsoft/microsoft-decision-1", STATE, QUESTIONS, recorder=recorder, context=make_context()
    )
    await client.aclose()

    speaker = result.choice("speaker")
    assert (speaker.choice, speaker.confidence) == ("mai", 0.82)
    assert speaker.probabilities == {"mai": 0.82, "narrator": 0.18}
    assert result.noul("lore__a") == 0.73
    assert result.score("tension") == 2.6
    assert result.usage.cost == 0.0002
    assert result.model == "microsoft/microsoft-decision-1"
    assert result.used_fallback is False
    assert len(recorder.calls) == 1

    sent = json.loads(requests[0].content)
    assert sent["model"] == "microsoft/microsoft-decision-1"
    assert sent["state"] == STATE
    assert sent["questions"]["speaker"]["type"] == "choice"
    assert sent["questions"]["lore__a"] == {"type": "noul", "instructions": "Có cần thông tin A không?"}
    assert sent["questions"]["tension"]["criteria"] == ["Thoải mái", "Bình thường", "Căng"]


async def test_budget_enforced_before_any_network_call() -> None:
    requests: list[httpx.Request] = []
    client, _ = make_client(route(requests), max_questions=2)
    for impl in (
        OpenRouterDecisionClient(client),
        ChatFallbackDecisionClient(client),
        ResilientDecisionClient(OpenRouterDecisionClient(client), ChatFallbackDecisionClient(client)),
    ):
        with pytest.raises(QuestionBudgetExceeded):
            await impl.decide(FAKE_KEY, "m/decision", STATE, QUESTIONS)
    await client.aclose()
    assert requests == []


async def test_fallback_on_404_records_usage_once() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/alpha/decisions":
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(200, json=load_json("fallback_decisions_chat.json"))

    client, _ = make_client(handler)
    recorder = FakeRecorder()
    resilient = ResilientDecisionClient(OpenRouterDecisionClient(client), ChatFallbackDecisionClient(client))
    result = await resilient.decide(
        FAKE_KEY, "microsoft/microsoft-decision-1", STATE, QUESTIONS, recorder=recorder, context=make_context()
    )
    await client.aclose()

    assert [r.url.path for r in requests] == ["/api/alpha/decisions", "/api/v1/chat/completions"]
    assert result.used_fallback is True
    assert len(recorder.calls) == 1  # the failed alpha call had no usage; only the chat call is billed
    assert recorder.calls[0][3] == "deepseek/deepseek-v4.1-flash-1017"

    # Fallback normalization: probabilities are renormalized, the choice is the argmax, score is clamped.
    speaker = result.choice("speaker")
    assert speaker.choice == "mai"
    assert speaker.probabilities == {"mai": 0.75, "narrator": 0.25}
    assert speaker.confidence == 0.75
    assert result.noul("lore__a") == 0.7
    assert result.score("tension") == 2.0

    chat_body = json.loads(requests[1].content)
    assert chat_body["response_format"]["type"] == "json_schema"
    assert chat_body["response_format"]["json_schema"]["strict"] is True
    assert "Quán cà phê buổi chiều" in chat_body["messages"][0]["content"]


async def test_fallback_on_unparseable_primary_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/alpha/decisions":
            return httpx.Response(200, json={"answers": {"speaker": {"choice": 5}}})
        return httpx.Response(200, json=load_json("fallback_decisions_chat.json"))

    client, _ = make_client(handler)
    resilient = ResilientDecisionClient(OpenRouterDecisionClient(client), ChatFallbackDecisionClient(client))
    result: DecisionResult = await resilient.decide(FAKE_KEY, "m/decision", STATE, QUESTIONS)
    await client.aclose()
    assert result.used_fallback is True


async def test_no_fallback_on_auth_error() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(401, json={"error": {"message": "no"}})

    client, _ = make_client(handler)
    resilient = ResilientDecisionClient(OpenRouterDecisionClient(client), ChatFallbackDecisionClient(client))
    with pytest.raises(LLMError) as info:
        await resilient.decide(FAKE_KEY, "m/decision", STATE, QUESTIONS)
    await client.aclose()
    assert info.value.status == 401
    assert len(requests) == 1


async def test_fallback_after_5xx_retries_exhausted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/alpha/decisions":
            return httpx.Response(503, text="down")
        return httpx.Response(200, json=load_json("fallback_decisions_chat.json"))

    client, delays = make_client(handler, max_retries=2)
    resilient = ResilientDecisionClient(OpenRouterDecisionClient(client), ChatFallbackDecisionClient(client))
    result = await resilient.decide(FAKE_KEY, "m/decision", STATE, QUESTIONS)
    await client.aclose()
    assert result.used_fallback is True
    assert len(delays) == 2
