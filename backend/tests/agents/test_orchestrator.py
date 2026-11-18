from __future__ import annotations

import uuid

from app.agents.base import AgentContext
from app.agents.orchestrator import (
    CORE_CARD_FIELDS,
    NARRATOR_ID,
    AgentConfig,
    OrchestratorInput,
    build_questions,
    run,
)
from app.formats.card import Secret, VietrpCard
from app.formats.lorebook import LorebookEntry
from app.llm.deps import LLMServices
from app.llm.fake import RecordedLLM
from app.pipeline.lorebook import LoreHit
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _hit(entry_id: str) -> LoreHit:
    entry = LorebookEntry(id=entry_id, title=entry_id, content=f"nội dung {entry_id}")
    return LoreHit(uuid.uuid4(), entry, 10, "candidate")


def _input(name: str = "Mai", candidates: bool = True) -> OrchestratorInput:
    card = VietrpCard(
        name=name,
        age=20,
        appearance="tóc ngắn",
        backstory="từng sống ở Huế",
        secrets=[Secret(id="bi_mat", content="nợ nần", reveal_when="khi bị hỏi thẳng")],
    )
    return OrchestratorInput(
        card=card,
        character_id="mai",
        user_name="Nam",
        user_message="Chào Mai, hôm nay quán đông không?",
        recent=["Nam: hi", "Mai: chào"],
        candidates=[_hit("quan_cafe"), _hit("gia_dinh")] if candidates else [],
    )


def _ctx(llm: RecordedLLM) -> tuple[AgentContext, LLMServices]:
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=gateway.chat_id, llm=gateway, settings=make_settings())
    return ctx, services


async def test_happy_path_plans_the_turn() -> None:
    ctx, services = _ctx(RecordedLLM.from_dir(names=["orchestrator_ok.json", "wiring_models.json"]))
    try:
        result = await run(ctx, AgentConfig(), _input())
    finally:
        await services.aclose()
    plan = result.value
    assert not plan.fallback and result.notices == []
    assert (plan.turn_type, plan.speaker_kind, plan.speaker_id, plan.addressed_to) == (
        "dialogue",
        "character",
        "mai",
        "character",
    )
    assert plan.lore_entry_ids == ["quan_cafe"]
    assert plan.card_fields == [*CORE_CARD_FIELDS, "backstory"]
    assert plan.secret_ids == []
    event = plan.to_event()
    assert event.speakers[0].id == "mai" and event.lore_ids == ["quan_cafe"]
    assert result.usage[0].prompt_tokens == 300


async def test_narrator_answer_and_no_optional_questions_for_empty_fields() -> None:
    inp = OrchestratorInput(
        card=VietrpCard(name="Lan", age=19), character_id="lan", user_name="Nam", user_message="Trời tối dần."
    )
    ctx, services = _ctx(RecordedLLM.from_dir(names=["orchestrator_narrator.json", "wiring_models.json"]))
    try:
        result = await run(ctx, AgentConfig(), inp)
    finally:
        await services.aclose()
    plan = result.value
    assert (plan.speaker_kind, plan.speaker_id, plan.turn_type) == ("narrator", NARRATOR_ID, "narration")
    assert plan.card_fields == list(CORE_CARD_FIELDS) and not plan.fallback


async def test_falls_back_to_narrator_with_notice_when_the_call_fails() -> None:
    llm = RecordedLLM.from_dir(names=["orchestrator_ok.json", "wiring_models.json"])
    llm.add([{"status": 400, "json": {"error": {"message": "bad"}}}], {"path": "/api/alpha/decisions"})
    # A card name the happy fixture does not match, so the failing fixture answers.
    ctx, services = _ctx(llm)
    try:
        result = await run(ctx, AgentConfig(), _input(name="Zed"))
    finally:
        await services.aclose()
    plan = result.value
    assert plan.fallback and plan.speaker_kind == "narrator" and plan.card_fields == list(CORE_CARD_FIELDS)
    assert [n.code for n in result.notices] == ["orchestrator_fallback"]
    assert "sk-or" not in repr(result)


def test_question_budget_caps_lore_candidates() -> None:
    inp = _input()
    fixed = len(build_questions(AgentConfig(), _input(candidates=False), 40))
    questions = build_questions(AgentConfig(), inp, fixed + 1)
    assert len(questions) == fixed + 1
    assert "lore__quan_cafe" in questions and "lore__gia_dinh" not in questions
    assert len(build_questions(AgentConfig(max_lore_questions=0), inp, 40)) == fixed
