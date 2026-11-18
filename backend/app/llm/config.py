"""LLM-layer settings that are not in `core/config.py`, plus a snapshot of the ones that are."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class LLMConfig:
    base_url: str = "https://openrouter.ai"
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 120.0
    max_retries: int = 3
    backoff_base_seconds: float = 2.0
    max_questions: int = 40
    # Optional attribution header for OpenRouter rankings; empty means "do not send".
    http_referer: str = ""
    app_title: str = "VietRP Studio"
    # Never sleep longer than this on a Retry-After header; a buggy upstream must not stall a turn.
    max_retry_after_seconds: float = 30.0
    # The model list changes rarely; one hour keeps price estimates fresh without hammering the endpoint.
    pricing_ttl_seconds: float = 3600.0
    # After a failed model-list fetch, wait this long before trying again.
    pricing_failure_retry_seconds: float = 60.0
    # EMA smoothing for the per-model token correction factor: 0.3 adapts within a few turns yet damps outliers.
    correction_alpha: float = 0.3
    correction_min: float = 0.8
    correction_max: float = 2.0
    # Fixed per-message overhead (role markers) added to the token estimate.
    tokens_per_message: int = 4
    # Fallback chat calls must be deterministic.
    fallback_temperature: float = 0.0
    fallback_max_tokens: int = 2000

    @classmethod
    def from_settings(cls, settings: Settings, **overrides: Any) -> LLMConfig:
        base = cls(
            base_url=settings.openrouter_base_url.rstrip("/"),
            connect_timeout_seconds=settings.http_connect_timeout_seconds,
            read_timeout_seconds=settings.http_timeout_seconds,
            max_retries=settings.llm_max_retries,
            backoff_base_seconds=settings.llm_backoff_base_seconds,
            max_questions=settings.decisions_max_questions,
        )
        return replace(base, **overrides) if overrides else base
