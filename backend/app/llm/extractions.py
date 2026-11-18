"""Extractions: pull named text fields out of a passage (OpenRouter alpha API, with a chat fallback)."""

from __future__ import annotations

import logging
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from app.llm.chat import ChatParams, complete_chat
from app.llm.client import LLMError, OpenRouterClient
from app.llm.decisions import QuestionBudgetExceeded, parse_json_object, should_fall_back
from app.llm.defaults import FALLBACK_CHAT_MODEL
from app.llm.templating import render
from app.llm.usage import Usage, UsageContext, UsageRecorder, record_usage

logger = logging.getLogger(__name__)

EXTRACTIONS_PATH = "/api/alpha/extractions"


class Field(BaseModel):
    type: Literal["text"] = "text"
    instructions: str


class ExtractedValue(BaseModel):
    value: str
    confidence: float


class ExtractionResult(BaseModel):
    values: dict[str, ExtractedValue]
    usage: Usage
    model: str
    used_fallback: bool = False


class ExtractionClient(Protocol):
    async def extract(
        self,
        api_key: str,
        model: str,
        state: str,
        fields: dict[str, Field],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> ExtractionResult: ...


def _bad(message: str) -> LLMError:
    return LLMError("llm_bad_response", None, message)


def _confidence(raw: Any, name: str) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise _bad(f"confidence of {name!r} is not a number")
    return min(1.0, max(0.0, float(raw)))


def normalize_values(raw_answers: Any, fields: dict[str, Field]) -> dict[str, ExtractedValue]:
    if not isinstance(raw_answers, dict):
        raise _bad("response has no answers object")
    out: dict[str, ExtractedValue] = {}
    for name in fields:
        raw = raw_answers.get(name)
        if not isinstance(raw, dict):
            raise _bad(f"missing answer for {name!r}")
        value = raw.get("value")
        # A null value means "not found"; keep it as an empty string with whatever confidence was given.
        if value is not None and not isinstance(value, str):
            raise _bad(f"value of {name!r} is not a string")
        out[name] = ExtractedValue(value=value or "", confidence=_confidence(raw.get("confidence"), name))
    return out


class OpenRouterExtractionClient:
    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client

    async def extract(
        self,
        api_key: str,
        model: str,
        state: str,
        fields: dict[str, Field],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> ExtractionResult:
        if len(fields) > self._client.cfg.max_questions:
            raise QuestionBudgetExceeded(len(fields), self._client.cfg.max_questions)
        if recorder is not None and context is None:
            raise ValueError("a usage recorder needs a UsageContext")
        body = {"model": model, "state": state, "fields": {k: f.model_dump() for k, f in fields.items()}}
        data = await self._client.post_json(EXTRACTIONS_PATH, api_key, body)
        if not isinstance(data, dict):
            raise _bad("response is not an object")
        usage = Usage.from_api(data.get("usage"))
        await record_usage(recorder, context, model, usage)
        values = normalize_values(data.get("answers"), fields)
        returned_model = data.get("model")
        return ExtractionResult(
            values=values, usage=usage, model=returned_model if isinstance(returned_model, str) else model
        )


def build_extraction_schema(fields: dict[str, Field]) -> dict[str, Any]:
    item = {
        "type": "object",
        "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}},
        "required": ["value", "confidence"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {name: item for name in fields},
        "required": list(fields),
        "additionalProperties": False,
    }


class ChatFallbackExtractionClient:
    def __init__(self, client: OpenRouterClient, chat_model: str = FALLBACK_CHAT_MODEL) -> None:
        self._client = client
        self._chat_model = chat_model

    async def extract(
        self,
        api_key: str,
        model: str,
        state: str,
        fields: dict[str, Field],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> ExtractionResult:
        cfg = self._client.cfg
        if len(fields) > cfg.max_questions:
            raise QuestionBudgetExceeded(len(fields), cfg.max_questions)
        prompt = render("extractions_fallback.j2", state=state, fields={k: f.model_dump() for k, f in fields.items()})
        params = ChatParams(
            temperature=cfg.fallback_temperature,
            max_tokens=cfg.fallback_max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "extractions", "strict": True, "schema": build_extraction_schema(fields)},
            },
        )
        text, usage = await complete_chat(
            self._client,
            api_key,
            self._chat_model,
            [{"role": "user", "content": prompt}],
            params,
            recorder=recorder,
            context=context,
        )
        values = normalize_values(parse_json_object(text), fields)
        return ExtractionResult(values=values, usage=usage, model=self._chat_model, used_fallback=True)


class ResilientExtractionClient:
    def __init__(self, primary: ExtractionClient, fallback: ExtractionClient) -> None:
        self._primary = primary
        self._fallback = fallback

    async def extract(
        self,
        api_key: str,
        model: str,
        state: str,
        fields: dict[str, Field],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> ExtractionResult:
        try:
            return await self._primary.extract(api_key, model, state, fields, recorder=recorder, context=context)
        except QuestionBudgetExceeded:
            raise
        except LLMError as exc:
            if not should_fall_back(exc):
                raise
            logger.warning("extractions primary failed (%s); using chat fallback", exc.code)
        result = await self._fallback.extract(api_key, model, state, fields, recorder=recorder, context=context)
        return result.model_copy(update={"used_fallback": True})
