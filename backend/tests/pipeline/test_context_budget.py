from __future__ import annotations

from app.llm.tokenizer import CorrectionTable
from app.pipeline.context_budget import BudgetSettings, estimate_tokens, needs_summary, usage_ratio


def test_needs_summary_threshold() -> None:
    cfg = BudgetSettings(context_length=1000, summarize_at=0.8)
    assert not needs_summary(799, cfg)
    assert needs_summary(800, cfg)
    assert usage_ratio(500, cfg) == 0.5


def test_from_memory_defaults_and_validation() -> None:
    assert BudgetSettings.from_memory(None).summarize_at == 0.8
    cfg = BudgetSettings.from_memory({"context_length": 4000, "summarize_at": 0.5})
    assert (cfg.context_length, cfg.summarize_at) == (4000, 0.5)
    bad = BudgetSettings.from_memory({"context_length": -1, "summarize_at": 5})
    assert bad.context_length > 0
    assert bad.summarize_at == 0.8


def test_prompt_budget_reserves_reply() -> None:
    assert BudgetSettings(context_length=2000, response_reserve=500).prompt_budget == 1500
    assert BudgetSettings(context_length=100, response_reserve=500).prompt_budget == 0


def test_correction_factor_scales_estimate() -> None:
    table = CorrectionTable()
    messages = [{"role": "user", "content": "xin chào các bạn " * 20}]
    base = estimate_tokens(table, "m", messages)
    table.observe("m", base, base * 2)
    assert estimate_tokens(table, "m", messages) > base
    assert estimate_tokens(table, "other", messages) == base
