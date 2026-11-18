"""Shared OpenRouter HTTP client: auth headers, retries with backoff, safe errors."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from app.llm.config import LLMConfig

# Transient statuses worth retrying (AGENTS.md section 4.4; same set as the reference engine).
RETRY_STATUSES = frozenset({429, 500, 502, 503, 529})
# How much of an upstream error body may appear in an error message.
MAX_ERROR_BODY_CHARS = 300


class LLMError(Exception):
    """An LLM call failed. `message` is English, safe to log, and never contains the API key."""

    def __init__(self, code: str, status: int | None, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.status = status
        self.message = message


def _code_for_status(status: int) -> str:
    if status in (401, 403):
        return "llm_auth_failed"
    if status == 402:
        return "llm_insufficient_credits"
    if status == 404:
        return "llm_not_found"
    if status == 429:
        return "llm_rate_limited"
    if status >= 500:
        return "llm_upstream_error"
    return "llm_bad_request"


def scrub(text: str, api_key: str | None) -> str:
    """Remove the API key from text that may be echoed back by a proxy or an upstream error."""
    if api_key and api_key in text:
        return text.replace(api_key, "[redacted]")
    return text


def error_from_body(status: int, body: bytes, api_key: str | None) -> LLMError:
    text = body.decode("utf-8", errors="replace")
    detail = text
    try:
        parsed = json.loads(text)
        err = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(err, dict) and isinstance(err.get("message"), str):
            detail = err["message"]
        elif isinstance(err, str):
            detail = err
    except ValueError:
        pass
    detail = scrub(detail, api_key)[:MAX_ERROR_BODY_CHARS]
    return LLMError(_code_for_status(status), status, f"HTTP {status}: {detail}")


def _retry_after_seconds(response: httpx.Response, cfg: LLMConfig) -> float | None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return None
    try:
        return min(max(float(raw), 0.0), cfg.max_retry_after_seconds)
    except ValueError:
        return None  # HTTP-date form is not worth parsing; fall back to exponential backoff


class OpenRouterClient:
    """One shared `httpx.AsyncClient` for all LLM calls. The API key is passed per call, never stored."""

    def __init__(
        self,
        cfg: LLMConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.cfg = cfg
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=cfg.base_url,
            timeout=httpx.Timeout(cfg.read_timeout_seconds, connect=cfg.connect_timeout_seconds),
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self, api_key: str | None) -> dict[str, str]:
        headers = {"X-Title": self.cfg.app_title}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if self.cfg.http_referer:
            headers["HTTP-Referer"] = self.cfg.http_referer
        return headers

    async def _send(
        self, method: str, path: str, api_key: str | None, body: dict[str, Any] | None, *, stream: bool
    ) -> httpx.Response:
        """Send with retries. On success the response is returned open (stream) or fully read."""
        attempt = 0
        while True:
            retry_after: float | None = None
            try:
                request = self._http.build_request(method, path, json=body, headers=self._headers(api_key))
                response = await self._http.send(request, stream=stream)
            except httpx.TimeoutException as exc:
                error = LLMError("llm_timeout", None, f"request timed out ({type(exc).__name__})")
            except httpx.TransportError as exc:
                error = LLMError("llm_network_error", None, f"network error ({type(exc).__name__})")
            else:
                if response.status_code < 400:
                    return response
                await response.aread()
                await response.aclose()
                error = error_from_body(response.status_code, response.content, api_key)
                if response.status_code not in RETRY_STATUSES:
                    raise error
                retry_after = _retry_after_seconds(response, self.cfg)
            if attempt >= self.cfg.max_retries:
                raise error
            delay = retry_after if retry_after is not None else self.cfg.backoff_base_seconds * (2**attempt)
            attempt += 1
            await self._sleep(delay)

    async def post_json(self, path: str, api_key: str, body: dict[str, Any]) -> Any:
        response = await self._send("POST", path, api_key, body, stream=False)
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError("llm_bad_response", response.status_code, "response body is not valid JSON") from exc

    async def get_json(self, path: str, api_key: str | None = None) -> Any:
        response = await self._send("GET", path, api_key, None, stream=False)
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError("llm_bad_response", response.status_code, "response body is not valid JSON") from exc

    @asynccontextmanager
    async def stream_post(self, path: str, api_key: str, body: dict[str, Any]) -> AsyncIterator[httpx.Response]:
        """Open a streaming POST. Retries only cover the time before the first byte of a 2xx response."""
        response = await self._send("POST", path, api_key, body, stream=True)
        try:
            yield response
        finally:
            await response.aclose()
