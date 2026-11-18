from __future__ import annotations

import pytest

from app.llm import tokenizer
from app.llm.config import LLMConfig
from app.llm.tokenizer import CorrectionTable, count_messages, count_text


@pytest.fixture(scope="module")
def encoding_available() -> None:
    try:
        tokenizer._encoding()
    except Exception as exc:  # network blocked while fetching the BPE file
        pytest.skip(f"tiktoken o200k_base could not be loaded (needs a one-time download): {type(exc).__name__}")


@pytest.mark.usefixtures("encoding_available")
def test_count_text_sanity() -> None:
    assert count_text("") == 0
    assert count_text("hello world") == 2  # known o200k_base result
    assert count_text("xin chào") >= 2
    assert count_text("<|endoftext|>") > 0  # special-token text is counted, not rejected
    assert count_text("a" * 1000) < 1000


@pytest.mark.usefixtures("encoding_available")
def test_count_messages_adds_per_message_overhead() -> None:
    messages = [{"role": "system", "content": "hello world"}, {"role": "user", "content": "hello world"}]
    assert count_messages(messages) == 2 * (2 + 4)
    assert count_messages(messages, per_message=0) == 4


@pytest.mark.usefixtures("encoding_available")
def test_estimate_applies_correction() -> None:
    table = CorrectionTable()
    messages = [{"role": "user", "content": "hello world"}]
    base = table.estimate("m/x", messages)
    assert base == 6
    table._factors["m/x"] = 1.5
    assert table.estimate("m/x", messages) == 9
    assert table.estimate("m/other", messages) == base  # factors are per model


def test_ema_moves_toward_ratio() -> None:
    table = CorrectionTable(LLMConfig(correction_alpha=0.5))
    assert table.factor("m") == 1.0
    assert table.observe("m", 100, 120) == pytest.approx(1.1)  # 0.5*1.0 + 0.5*1.2
    assert table.observe("m", 100, 120) == pytest.approx(1.15)


def test_ema_clamps_to_range() -> None:
    table = CorrectionTable(LLMConfig(correction_alpha=1.0))
    assert table.observe("m", 100, 1000) == 2.0
    assert table.observe("m", 100, 1) == 0.8


def test_ema_ignores_degenerate_samples() -> None:
    table = CorrectionTable()
    table.observe("m", 0, 100)
    table.observe("m", 100, 0)
    assert table.factor("m") == 1.0
