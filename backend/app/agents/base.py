"""Agent framework: the context every agent receives, its result type, and the LLM gateway.

`LLMGateway` is the only way agents reach the LLM layer. It reads the API key per call, prices and records every
call in `usage_log`, feeds real prompt-token counts back into the correction table, and collects the usage so the
turn can emit `usage` events. Internal `Notice` objects are mapped to SSE `notice` events by the pipeline (WP-O).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.config import Settings
from app.llm.chat import ChatEvent, ChatMessage, ChatParams, complete_chat, stream_chat
from app.llm.client import LLMError
from app.llm.decisions import DecisionResult, Question
from app.llm.deps import LLMServices
from app.llm.extractions import ExtractionResult
from app.llm.extractions import Field as ExtractionField
from app.llm.tokenizer import count_messages
from app.llm.usage import NullUsageRecorder, Usage, UsageContext, UsageRecorder

logger = logging.getLogger(__name__)


# Returns the OpenRouter key for the current vault. Called once per LLM call; the result is never stored.
ApiKeyProvider = Callable[[], Awaitable[str]]


@dataclass(frozen=True, slots=True)
class Notice:
    """A non-fatal problem the user should hear about. Mapped to the `notice` SSE event later."""

    code: str
    agent: str
    detail: str = ""


@dataclass(slots=True)
class AgentResult[T]:
    value: T
    usage: list[Usage] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)


class _PricingRecorder:
    """Wraps the real recorder: fills in a missing cost from the pricing cache, then collects and persists."""

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    async def record(
        self, vault_id: uuid.UUID, chat_id: uuid.UUID | None, agent: str, model: str, usage: Usage
    ) -> None:
        priced = await self._gateway.price(model, usage)
        self._gateway.collected.append(priced)
        await self._gateway.recorder.record(vault_id, chat_id, agent, model, priced)


class LLMGateway:
    """Per-turn facade over chat, streaming, Decisions and Extractions."""

    def __init__(
        self,
        services: LLMServices,
        *,
        vault_id: uuid.UUID,
        chat_id: uuid.UUID | None,
        api_key: ApiKeyProvider,
        recorder: UsageRecorder | None = None,
    ) -> None:
        self._services = services
        self.vault_id = vault_id
        self.chat_id = chat_id
        self._api_key = api_key
        self.recorder: UsageRecorder = recorder or NullUsageRecorder()
        # Every priced usage of this gateway, in call order, until `drain_usage()`.
        self.collected: list[Usage] = []

    def _context(self, agent: str) -> UsageContext:
        return UsageContext(vault_id=self.vault_id, chat_id=self.chat_id, agent=agent)

    async def price(self, model: str, usage: Usage) -> Usage:
        """Provider-reported cost when present, else tokens times the listed price, else unchanged."""
        if usage.cost is not None:
            return usage
        cost = await self._services.pricing.estimate_cost(model, usage)
        return usage if cost is None else usage.model_copy(update={"cost": cost})

    def _observe(self, model: str, messages: list[ChatMessage], usage: Usage) -> None:
        raw = count_messages(messages, per_message=self._services.cfg.tokens_per_message)
        self._services.corrections.observe(model, raw, usage.prompt_tokens)

    def drain_usage(self) -> list[Usage]:
        """Usage collected since the last drain; the caller turns it into `usage` events."""
        out, self.collected = self.collected, []
        return out

    async def complete(
        self, agent: str, model: str, messages: list[ChatMessage], params: ChatParams | None = None
    ) -> tuple[str, Usage]:
        text, usage = await complete_chat(
            self._services.client,
            await self._api_key(),
            model,
            messages,
            params,
            recorder=_PricingRecorder(self),
            context=self._context(agent),
        )
        self._observe(model, messages, usage)
        return text, await self.price(model, usage)

    async def stream(
        self, agent: str, model: str, messages: list[ChatMessage], params: ChatParams | None = None
    ) -> AsyncIterator[ChatEvent]:
        """Yields deltas, finishes and one final priced `Usage`; usage is recorded when the stream ends."""
        events = stream_chat(
            self._services.client,
            await self._api_key(),
            model,
            messages,
            params,
            recorder=_PricingRecorder(self),
            context=self._context(agent),
        )
        try:
            async for event in events:
                if isinstance(event, Usage):
                    self._observe(model, messages, event)
                    yield await self.price(model, event)
                else:
                    yield event
        finally:
            # Closing an abandoned stream (stop button) still records the usage seen so far.
            await events.aclose()  # type: ignore[attr-defined]

    async def decide(
        self, agent: str, model: str, state: dict[str, str], questions: dict[str, Question]
    ) -> DecisionResult:
        result = await self._services.decisions.decide(
            await self._api_key(),
            model,
            state,
            questions,
            recorder=_PricingRecorder(self),
            context=self._context(agent),
        )
        return result.model_copy(update={"usage": await self.price(model, result.usage)})

    async def extract(self, agent: str, model: str, state: str, fields: dict[str, ExtractionField]) -> ExtractionResult:
        result = await self._services.extractions.extract(
            await self._api_key(), model, state, fields, recorder=_PricingRecorder(self), context=self._context(agent)
        )
        return result.model_copy(update={"usage": await self.price(model, result.usage)})


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class AgentContext:
    vault_id: uuid.UUID
    chat_id: uuid.UUID | None
    llm: LLMGateway
    settings: Settings
    clock: Callable[[], datetime] = _utc_now


def _safe_detail(exc: Exception) -> str:
    """Notice text for an exception. Only the LLMError code is used: free text could echo upstream content."""
    return exc.code if isinstance(exc, LLMError) else type(exc).__name__


async def run_non_critical[T](agent_id: str, work: Awaitable[AgentResult[T]]) -> AgentResult[T | None]:
    """Await a non-critical agent (AGENTS.md section 4.4). A failure becomes a notice and the turn continues.

    Cancellation (the user pressed stop) is never swallowed.
    """
    try:
        result = await work
    except Exception as exc:
        detail = _safe_detail(exc)
        logger.warning("non-critical agent %s failed (%s)", agent_id, detail)
        return AgentResult[T | None](value=None, notices=[Notice(code="agent_failed", agent=agent_id, detail=detail)])
    return AgentResult[T | None](value=result.value, usage=result.usage, notices=result.notices)
