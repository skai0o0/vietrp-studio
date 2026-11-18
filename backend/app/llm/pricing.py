"""Model prices from `GET /api/v1/models`, cached with a TTL."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, TypedDict

from app.llm.client import LLMError, OpenRouterClient
from app.llm.usage import Usage

logger = logging.getLogger(__name__)

MODELS_PATH = "/api/v1/models"


class Price(TypedDict):
    """USD per token."""

    prompt: float
    completion: float


def _to_float(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None  # OpenRouter uses "-1" for variable-priced routers


class PricingCache:
    def __init__(self, client: OpenRouterClient, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._client = client
        self._clock = clock
        self._prices: dict[str, Price] = {}
        self._expires_at = 0.0
        self._lock = asyncio.Lock()

    async def refresh(self) -> None:
        """Fetch the model list. On failure keep stale data and retry after a short wait."""
        cfg = self._client.cfg
        try:
            data = await self._client.get_json(MODELS_PATH)
            prices: dict[str, Price] = {}
            for entry in data["data"]:
                pricing = entry.get("pricing") or {}
                prompt, completion = _to_float(pricing.get("prompt")), _to_float(pricing.get("completion"))
                if isinstance(entry.get("id"), str) and prompt is not None and completion is not None:
                    prices[entry["id"]] = {"prompt": prompt, "completion": completion}
        except (LLMError, KeyError, TypeError) as exc:
            logger.warning("model price refresh failed (%s)", getattr(exc, "code", type(exc).__name__))
            self._expires_at = self._clock() + cfg.pricing_failure_retry_seconds
            return
        self._prices = prices
        self._expires_at = self._clock() + cfg.pricing_ttl_seconds

    async def _ensure_fresh(self) -> None:
        if self._clock() < self._expires_at:
            return
        async with self._lock:
            if self._clock() >= self._expires_at:
                await self.refresh()

    async def price(self, model: str) -> Price | None:
        await self._ensure_fresh()
        return self._prices.get(model)

    async def estimate_cost(self, model: str, usage: Usage) -> float | None:
        """Provider-reported cost when present, else tokens times the listed price, else None."""
        if usage.cost is not None:
            return usage.cost
        price = await self.price(model)
        if price is None:
            return None
        # completion_tokens already includes reasoning tokens on OpenRouter.
        return usage.prompt_tokens * price["prompt"] + usage.completion_tokens * price["completion"]
