from __future__ import annotations

import httpx
import pytest

from app.llm.chat import complete_chat
from app.llm.client import LLMError
from tests.llm.helpers import FAKE_KEY, load_json, make_client

MESSAGES = [{"role": "user", "content": "Chào"}]


async def test_retries_429_honoring_retry_after() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={"error": {"message": "slow down"}})
        return httpx.Response(200, json=load_json("chat_complete.json"))

    client, delays = make_client(handler)
    text, _ = await complete_chat(client, FAKE_KEY, "m/x", MESSAGES)
    await client.aclose()
    assert text == "Đã rõ."
    assert len(calls) == 2
    assert delays == [7.0]


async def test_retry_after_is_capped() -> None:
    answers = iter(
        [
            httpx.Response(503, headers={"Retry-After": "9999"}),
            httpx.Response(200, json=load_json("chat_complete.json")),
        ]
    )
    client, delays = make_client(lambda r: next(answers), max_retry_after_seconds=30.0)
    await complete_chat(client, FAKE_KEY, "m/x", MESSAGES)
    await client.aclose()
    assert delays == [30.0]


async def test_exponential_backoff_then_gives_up() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(502, text="bad gateway")

    client, delays = make_client(handler, max_retries=3, backoff_base_seconds=2.0)
    with pytest.raises(LLMError) as info:
        await complete_chat(client, FAKE_KEY, "m/x", MESSAGES)
    await client.aclose()
    assert len(calls) == 4  # first try + 3 retries
    assert delays == [2.0, 4.0, 8.0]
    assert info.value.status == 502
    assert info.value.code == "llm_upstream_error"


async def test_no_retry_on_400() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "invalid request"}})

    client, delays = make_client(handler)
    with pytest.raises(LLMError) as info:
        await complete_chat(client, FAKE_KEY, "m/x", MESSAGES)
    await client.aclose()
    assert len(calls) == 1 and delays == []
    assert info.value.code == "llm_bad_request"
    assert info.value.status == 400


async def test_api_key_never_in_error_message() -> None:
    # An upstream (or proxy) that echoes the Authorization header back must not leak the key through LLMError.
    def handler(request: httpx.Request) -> httpx.Response:
        echoed = request.headers["authorization"]
        return httpx.Response(401, json={"error": {"message": f"bad credentials: {echoed} / {FAKE_KEY}"}})

    client, _ = make_client(handler)
    with pytest.raises(LLMError) as info:
        await complete_chat(client, FAKE_KEY, "m/x", MESSAGES)
    await client.aclose()
    error = info.value
    assert FAKE_KEY not in error.message
    assert FAKE_KEY not in str(error)
    assert FAKE_KEY not in repr(error)
    assert error.code == "llm_auth_failed"


async def test_timeout_maps_to_llm_error_without_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timed out for {FAKE_KEY}", request=request)

    client, delays = make_client(handler, max_retries=1)
    with pytest.raises(LLMError) as info:
        await complete_chat(client, FAKE_KEY, "m/x", MESSAGES)
    await client.aclose()
    assert info.value.code == "llm_timeout"
    assert FAKE_KEY not in str(info.value)
    assert len(delays) == 1
