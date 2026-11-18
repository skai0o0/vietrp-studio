"""Token estimation (tiktoken o200k_base) with a per-model correction learned from real usage."""

from __future__ import annotations

import math
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import tiktoken

from app.llm.config import LLMConfig

if TYPE_CHECKING:
    from collections.abc import Sequence

ENCODING_NAME = "o200k_base"


@lru_cache
def _encoding() -> tiktoken.Encoding:
    # Loaded lazily: the first call may download the BPE file, so importing this module stays cheap.
    return tiktoken.get_encoding(ENCODING_NAME)


def count_text(text: str) -> int:
    # disallowed_special=() so user text containing "<|endoftext|>" is counted instead of raising.
    return len(_encoding().encode(text, disallowed_special=()))


def count_messages(messages: Sequence[dict[str, Any]], *, per_message: int | None = None) -> int:
    overhead = LLMConfig().tokens_per_message if per_message is None else per_message
    total = 0
    for message in messages:
        content = message.get("content") or ""
        total += count_text(content if isinstance(content, str) else str(content)) + overhead
    return total


class CorrectionTable:
    """Per-model EMA of `real_prompt_tokens / raw_estimate`, clamped so one odd sample cannot wreck the budget."""

    def __init__(self, cfg: LLMConfig | None = None) -> None:
        self._cfg = cfg or LLMConfig()
        self._factors: dict[str, float] = {}

    def factor(self, model: str) -> float:
        return self._factors.get(model, 1.0)

    def observe(self, model: str, raw_estimate: int, real_prompt_tokens: int) -> float:
        """Fold one real measurement in; returns the new factor. Non-positive inputs are ignored."""
        if raw_estimate <= 0 or real_prompt_tokens <= 0:
            return self.factor(model)
        alpha = self._cfg.correction_alpha
        updated = (1 - alpha) * self.factor(model) + alpha * (real_prompt_tokens / raw_estimate)
        updated = min(self._cfg.correction_max, max(self._cfg.correction_min, updated))
        self._factors[model] = updated
        return updated

    def estimate(self, model: str, messages: Sequence[dict[str, Any]]) -> int:
        raw = count_messages(messages, per_message=self._cfg.tokens_per_message)
        return math.ceil(raw * self.factor(model))
