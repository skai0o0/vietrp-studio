from __future__ import annotations

from app.agents.base import AgentContext, AgentResult
from app.agents.director import AgentConfig, DirectorInput, DirectorOutcome, better, fix_hints, run
from app.llm.fake import RecordedLLM
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


async def _judge(fixture: str, draft: str, attempt: int = 0) -> AgentResult[DirectorOutcome]:
    gateway, services, _, _ = make_gateway(RecordedLLM.from_dir(names=[fixture, "wiring_models.json"]))
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=gateway.chat_id, llm=gateway, settings=make_settings())
    inp = DirectorInput("Mai", "Nam", "Chào Mai", draft, attempt)
    try:
        return await run(ctx, AgentConfig(), inp)
    finally:
        await services.aclose()


async def test_pass_gives_per_criterion_probabilities_and_priority() -> None:
    result = await _judge("director_pass.json", "Mai ngẩng lên.")
    outcome = result.value
    assert outcome.passed and outcome.priority == 1
    assert [c.id for c in outcome.verdict.criteria] == [
        "answers_last",
        "no_new_events",
        "no_player_voice",
        "no_assistant_voice",
    ]
    # Probabilities are "criterion satisfied", also for the "bad when yes" questions.
    assert outcome.verdict.criteria[1].probability == 0.95
    assert all(c.passed and c.hint_vi == "" for c in outcome.verdict.criteria)
    assert 0.9 < outcome.score <= 1.0 and fix_hints(outcome.verdict) == []


async def test_fail_carries_vietnamese_hints_for_failed_criteria_only() -> None:
    result = await _judge("director_fail.json", "Mai nhìn đồng hồ rồi đi mất.", attempt=1)
    outcome = result.value
    assert not outcome.passed and outcome.verdict.attempt == 1 and outcome.priority == 0
    failed = {c.id: c for c in outcome.verdict.criteria if not c.passed}
    assert set(failed) == {"no_new_events", "no_player_voice"}
    assert "Nam" in failed["no_player_voice"].hint_vi and failed["no_new_events"].hint_vi
    assert fix_hints(outcome.verdict) == [failed["no_new_events"].hint_vi, failed["no_player_voice"].hint_vi]


async def test_better_keeps_the_higher_score_and_the_earlier_on_ties() -> None:
    good = (await _judge("director_pass.json", "Mai ngẩng lên.")).value
    bad = (await _judge("director_fail.json", "Mai nhìn đồng hồ.")).value
    assert better(bad, good) is good and better(good, bad) is good and better(good, good) is good
