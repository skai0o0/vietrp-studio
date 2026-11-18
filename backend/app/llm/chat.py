"""Chat completions: streaming and non-streaming, with usage accounting."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from app.llm.client import LLMError, OpenRouterClient, scrub
from app.llm.usage import Usage, UsageContext, UsageRecorder, record_usage

CHAT_PATH = "/api/v1/chat/completions"

ChatMessage = dict[str, Any]


class ContentDelta(BaseModel):
    type: Literal["content"] = "content"
    text: str


class ReasoningDelta(BaseModel):
    type: Literal["reasoning"] = "reasoning"
    text: str


class Finish(BaseModel):
    type: Literal["finish"] = "finish"
    # "stop", "length", "tool_calls", ... as reported by the provider.
    reason: str


ChatEvent = ContentDelta | ReasoningDelta | Usage | Finish


class ChatParams(BaseModel):
    temperature: float = 1.0
    top_p: float = 0.95
    max_tokens: int = 1500
    # "off" disables reasoning; "auto" lets the model decide; "low" | "medium" | "high" set the effort.
    reasoning: str = "off"
    # OpenRouter provider routing, passed through untouched.
    provider: dict[str, Any] | None = None
    # e.g. a json_schema response format for the Decisions fallback.
    response_format: dict[str, Any] | None = None

    def to_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }
        if self.reasoning == "off":
            body["reasoning"] = {"enabled": False}
        elif self.reasoning == "auto":
            body["reasoning"] = {"enabled": True}
        else:
            body["reasoning"] = {"enabled": True, "effort": self.reasoning}
        if self.provider:
            body["provider"] = self.provider
        if self.response_format:
            body["response_format"] = self.response_format
        return body


def build_body(model: str, messages: list[ChatMessage], params: ChatParams, *, stream: bool) -> dict[str, Any]:
    return {
        "model": model,
        "messages": messages,
        "stream": stream,
        "usage": {"include": True},
        **params.to_body(),
    }


def _raise_if_error_chunk(chunk: dict[str, Any], api_key: str) -> None:
    err = chunk.get("error")
    if err:
        text = json.dumps(err, ensure_ascii=False)
        raise LLMError("llm_stream_error", None, scrub(text, api_key)[:300])


async def stream_chat(
    client: OpenRouterClient,
    api_key: str,
    model: str,
    messages: list[ChatMessage],
    params: ChatParams | None = None,
    *,
    recorder: UsageRecorder | None = None,
    context: UsageContext | None = None,
) -> AsyncIterator[ChatEvent]:
    """Stream a completion. Yields deltas, a `Finish` per finish reason, and one final `Usage`.

    Usage is recorded exactly once, when the stream ends (or is closed early after usage arrived).
    """
    if recorder is not None and context is None:
        raise ValueError("a usage recorder needs a UsageContext")
    body = build_body(model, messages, params or ChatParams(), stream=True)
    usage: Usage | None = None
    recorded = False
    try:
        async with client.stream_post(CHAT_PATH, api_key, body) as response:
            try:
                async for line in response.aiter_lines():
                    line = line.strip()
                    # Blank lines separate SSE events; ":" lines are comments such as ": OPENROUTER PROCESSING".
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(chunk, dict):
                        continue
                    _raise_if_error_chunk(chunk, api_key)
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        reasoning = delta.get("reasoning") or delta.get("reasoning_content")
                        if reasoning:
                            yield ReasoningDelta(text=reasoning)
                        if delta.get("content"):
                            yield ContentDelta(text=delta["content"])
                        if choice.get("finish_reason"):
                            yield Finish(reason=str(choice["finish_reason"]))
                    if chunk.get("usage"):
                        usage = Usage.from_api(chunk["usage"])
            except httpx.TimeoutException as exc:
                raise LLMError("llm_timeout", None, f"stream timed out ({type(exc).__name__})") from exc
            except httpx.TransportError as exc:
                raise LLMError("llm_network_error", None, f"stream interrupted ({type(exc).__name__})") from exc
        if usage is not None:
            yield usage
    finally:
        if usage is not None and not recorded:
            recorded = True
            await record_usage(recorder, context, model, usage)


async def complete_chat(
    client: OpenRouterClient,
    api_key: str,
    model: str,
    messages: list[ChatMessage],
    params: ChatParams | None = None,
    *,
    recorder: UsageRecorder | None = None,
    context: UsageContext | None = None,
) -> tuple[str, Usage]:
    if recorder is not None and context is None:
        raise ValueError("a usage recorder needs a UsageContext")
    body = build_body(model, messages, params or ChatParams(), stream=False)
    data = await client.post_json(CHAT_PATH, api_key, body)
    if isinstance(data, dict) and data.get("error"):
        raise LLMError("llm_upstream_error", None, scrub(json.dumps(data["error"], ensure_ascii=False), api_key)[:300])
    try:
        text = data["choices"][0]["message"].get("content") or ""
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise LLMError("llm_bad_response", None, "completion has no choices[0].message") from exc
    usage = Usage.from_api(data.get("usage"))
    await record_usage(recorder, context, model, usage)
    return text, usage
