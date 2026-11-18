from __future__ import annotations

import httpx
import pytest

from app.llm.defaults import AGENT_IDS, DEFAULT_EXTRACTIONS_MODEL, DEFAULT_MODELS
from app.llm.pricing import PricingCache
from app.llm.usage import Usage
from tests.llm.helpers import load_json, make_client


def test_default_models_cover_all_nine_agents() -> None:
    assert set(DEFAULT_MODELS) == set(AGENT_IDS)
    assert len(AGENT_IDS) == 9
    chat = "deepseek/deepseek-v4.1-flash-1017"
    decision = "microsoft/microsoft-decision-1"
    for agent in ("writer", "creator", "archivist", "bond_drafter"):
        assert DEFAULT_MODELS[agent] == chat  # type: ignore[index]
    for agent in ("orchestrator", "director", "state_keeper", "card_judge", "bond_selector"):
        assert DEFAULT_MODELS[agent] == decision  # type: ignore[index]
    assert DEFAULT_EXTRACTIONS_MODEL == decision


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_price_cached_until_ttl() -> None:
    fetches: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetches.append(1)
        assert request.url.path == "/api/v1/models"
        return httpx.Response(200, json=load_json("models.json"))

    client, _ = make_client(handler, pricing_ttl_seconds=100.0)
    clock = Clock()
    cache = PricingCache(client, clock=clock)

    price = await cache.price("deepseek/deepseek-v4.1-flash-1017")
    assert price == {"prompt": 2e-7, "completion": 8e-7}
    assert await cache.price("openrouter/auto") is None  # negative price = variable, unusable
    assert await cache.price("free/model") == {"prompt": 0.0, "completion": 0.0}
    assert await cache.price("unknown/model") is None
    assert len(fetches) == 1

    clock.now = 101.0
    await cache.price("free/model")
    assert len(fetches) == 2
    await client.aclose()


async def test_estimate_cost_prefers_provider_cost() -> None:
    client, _ = make_client(lambda r: httpx.Response(200, json=load_json("models.json")))
    cache = PricingCache(client)
    model = "deepseek/deepseek-v4.1-flash-1017"
    assert await cache.estimate_cost(model, Usage(prompt_tokens=1000, completion_tokens=500, cost=0.5)) == 0.5
    computed = await cache.estimate_cost(model, Usage(prompt_tokens=1000, completion_tokens=500))
    assert computed == pytest.approx(1000 * 2e-7 + 500 * 8e-7)
    assert await cache.estimate_cost("unknown/model", Usage(prompt_tokens=1)) is None
    await client.aclose()


async def test_failed_refresh_keeps_stale_data_and_backs_off() -> None:
    state = {"fail": False, "fetches": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["fetches"] += 1
        if state["fail"]:
            return httpx.Response(400, text="nope")
        return httpx.Response(200, json=load_json("models.json"))

    client, _ = make_client(handler, pricing_ttl_seconds=10.0, pricing_failure_retry_seconds=5.0)
    clock = Clock()
    cache = PricingCache(client, clock=clock)
    assert await cache.price("free/model") is not None
    state["fail"] = True
    clock.now = 11.0
    assert await cache.price("free/model") is not None  # stale data survives
    fetched = state["fetches"]
    clock.now = 13.0
    await cache.price("free/model")
    assert state["fetches"] == fetched  # still inside the failure back-off
    await client.aclose()
