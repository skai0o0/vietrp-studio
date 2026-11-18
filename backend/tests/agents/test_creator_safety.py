"""The Creator always carries the minor-safety rule, since a card's age is unknown while drafting."""

from __future__ import annotations

import pytest

from app.agents import creator
from app.pipeline import safety


def test_creator_rule_renders_and_mentions_minors() -> None:
    text = safety.creator_rule()
    assert "18 tuổi" in text
    assert "tình dục" in text


def test_interview_messages_carry_rule_before_history() -> None:
    msgs = creator.build_interview_messages(
        target_type="character",
        seed={},
        messages=[{"role": "user", "content": "Tạo nhân vật 16 tuổi"}],
        user_message="tiếp đi",
    )
    systems = [m for m in msgs if m["role"] == "system"]
    assert systems[-1]["content"] == safety.creator_rule()
    first_non_system = next(i for i, m in enumerate(msgs) if m["role"] != "system")
    assert all(m["role"] == "system" for m in msgs[:first_non_system])


def test_creator_rule_missing_template_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(safety, "CREATOR_RULE_TEMPLATE", "_shared/does_not_exist.j2")
    with pytest.raises(safety.SafetyConfigError):
        safety.creator_rule()
