"""Shared helpers for LLM-layer tests: fixture loading, mock transports, a recording recorder."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx

from app.llm.client import OpenRouterClient
from app.llm.config import LLMConfig
from app.llm.usage import Usage, UsageContext

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"

# Not a real key; the tests only check that it is never echoed.
FAKE_KEY = "sk-or-test-0000000000000000"

Handler = Callable[[httpx.Request], httpx.Response]


def load_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def load_json(name: str) -> Any:
    return json.loads(load_bytes(name))


class ChunkedStream(httpx.AsyncByteStream):
    """Delivers a body in fixed-size pieces so SSE lines get split mid-line."""

    def __init__(self, body: bytes, size: int) -> None:
        self._body = body
        self._size = size

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for i in range(0, len(self._body), self._size):
            yield self._body[i : i + self._size]


class FakeRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, uuid.UUID | None, str, str, Usage]] = []

    async def record(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, agent: str, model: str, usage: Usage
    ) -> None:
        self.calls.append((vault_id, chat_id, agent, model, usage))


def make_context(agent: str = "orchestrator") -> UsageContext:
    return UsageContext(vault_id=uuid.uuid4(), chat_id=None, agent=agent)


def make_client(handler: Handler, **cfg_overrides: Any) -> tuple[OpenRouterClient, list[float]]:
    """Client over a mock transport. Returns it plus the list of delays it slept (no real waiting)."""
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    cfg = LLMConfig(**cfg_overrides)
    client = OpenRouterClient(cfg, transport=httpx.MockTransport(handler), sleep=fake_sleep)
    return client, delays
