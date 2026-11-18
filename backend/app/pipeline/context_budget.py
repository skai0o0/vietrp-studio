"""Context budget: tiktoken estimate times a per-model correction factor (AGENTS.md section 4.5)."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.core.config import DEFAULT_CONTEXT_TOKENS, RESPONSE_RESERVE_TOKENS, SUMMARIZE_AT_DEFAULT
from app.llm.tokenizer import CorrectionTable, count_text


@dataclass(frozen=True, slots=True)
class BudgetSettings:
    """`memory.context_length` / `memory.summarize_at` from architecture section 3.1."""

    context_length: int = DEFAULT_CONTEXT_TOKENS
    summarize_at: float = SUMMARIZE_AT_DEFAULT
    response_reserve: int = RESPONSE_RESERVE_TOKENS

    @classmethod
    def from_memory(cls, memory: Mapping[str, Any] | None) -> BudgetSettings:
        data = memory or {}
        length = data.get("context_length")
        ratio = data.get("summarize_at")
        return cls(
            context_length=length if isinstance(length, int) and length > 0 else DEFAULT_CONTEXT_TOKENS,
            summarize_at=float(ratio) if isinstance(ratio, int | float) and 0 < ratio <= 1 else SUMMARIZE_AT_DEFAULT,
        )

    @property
    def prompt_budget(self) -> int:
        """Tokens available to the prompt once room for the reply is reserved."""
        return max(0, self.context_length - self.response_reserve)


def estimate_tokens(table: CorrectionTable, model: str, messages: Sequence[dict[str, Any]]) -> int:
    """Corrected token estimate for a message list."""
    return table.estimate(model, messages)


def estimate_text_tokens(table: CorrectionTable, model: str, text: str) -> int:
    return math.ceil(count_text(text) * table.factor(model))


def needs_summary(total_tokens: int, settings: BudgetSettings) -> bool:
    """True once the prompt reaches `summarize_at` of the context window (hook only; P4 runs the Archivist)."""
    return total_tokens >= settings.context_length * settings.summarize_at


def usage_ratio(total_tokens: int, settings: BudgetSettings) -> float:
    return total_tokens / settings.context_length if settings.context_length else 0.0
