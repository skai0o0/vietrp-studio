"""Unit tests for Card Judge agent and deterministic safety checks."""

from __future__ import annotations

import json
from typing import Any

from app.agents import card_judge
from app.agents.base import AgentContext
from app.formats.card import VietrpCard
from app.formats.world import Location, Opening, VietrpWorld
from app.llm.fake import RecordedLLM
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _decision_payload(overrides: dict[str, float] | None = None) -> dict[str, Any]:
    probs = {cid: 0.9 for cid in card_judge.CRITERIA}
    if overrides:
        probs.update(overrides)
    return {
        "status": 200,
        "json": {
            "model": "microsoft/microsoft-decision-1",
            "usage": {"prompt_tokens": 200, "completion_tokens": 12, "cost": 0.0002},
            "answers": {cid: {"noul": p} for cid, p in probs.items()},
        },
    }


def _sample_card(**overrides: Any) -> VietrpCard:
    data: dict[str, Any] = {
        "name": "Lan Anh",
        "age": 24,
        "tagline": "Thợ sửa đồng hồ trong con hẻm mưa.",
        "appearance": "Tóc búi bằng chiếc đũa gỗ, luôn đeo kính lúp thợ đồng hồ.",
        "personality": "Kiên nhẫn trước máy móc hỏng nhưng cộc lốc khi bị hỏi chuyện riêng.",
        "backstory": "Giữ tiệm sửa đồng hồ cũ của ông nội để tìm chủ nhân chiếc đồng hồ mất số.",
        "goals": "Tìm ra nguồn gốc chiếc đồng hồ bỏ túi bị cháy góc mặt số.",
        "greetings": ['*Ngẩng lên khỏi bàn sửa, ánh mắt dừng ở chiếc đồng hồ trên tay cậu.* "Hỏng kim hay đứng máy?"'],
    }
    data.update(overrides)
    return VietrpCard.model_validate(data)


def _sample_world(**overrides: Any) -> VietrpWorld:
    data: dict[str, Any] = {
        "name": "Phố Mưa 1998",
        "rules": "Đời thường thập niên 90 không phép thuật.",
        "locations": [
            Location(id="sai_gon", parent_id=None, level="province", name="Sài Gòn"),
            Location(id="quan_3", parent_id="sai_gon", level="district", name="Quận 3"),
            Location(id="tiem_tra", parent_id="quan_3", level="place", name="Tiệm trà cũ"),
        ],
        "openings": [
            Opening(id="mua_chieu", title="Chiều mưa", location_id="tiem_tra", message="Mưa rào đổ xuống mái tôn.")
        ],
    }
    data.update(overrides)
    return VietrpWorld.model_validate(data)


async def test_card_judge_evaluates_card_and_world_across_six_criteria() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([_decision_payload()], {"path": "/api/alpha/decisions"})
    gateway, services, recorder, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        card_res = await card_judge.run(ctx, card_judge.AgentConfig(), _sample_card())
        world_res = await card_judge.run(ctx, card_judge.AgentConfig(), _sample_world())
    finally:
        await services.aclose()

    for res in (card_res.value, world_res.value):
        assert res.passed is True
        assert res.threshold == 0.65
        assert res.score == 0.9
        assert [c.id for c in res.criteria] == list(card_judge.CRITERIA)
        assert all(c.passed and c.label and c.hint_vi == "" for c in res.criteria)

    assert [call[2] for call in recorder.calls] == ["card_judge", "card_judge"]


async def test_card_judge_failing_criteria_include_vietnamese_hints() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add(
        [_decision_payload({"no_command_tone": 0.25, "actionable_goals": 0.45})],
        {"path": "/api/alpha/decisions"},
    )
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        res = await card_judge.run(ctx, card_judge.AgentConfig(), _sample_card())
    finally:
        await services.aclose()

    verdict = res.value
    assert verdict.passed is False
    by_id = {c.id: c for c in verdict.criteria}
    assert by_id["no_command_tone"].passed is False and by_id["no_command_tone"].hint_vi
    assert by_id["actionable_goals"].passed is False and by_id["actionable_goals"].hint_vi
    assert by_id["completeness"].passed is True and by_id["completeness"].hint_vi == ""


async def test_card_judge_safety_fails_deterministically_on_missing_age_non_fictional_and_world_incomplete() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    # Model tries to pass safety_valid with 0.95; deterministic safety must override and fail.
    llm.add([_decision_payload({"safety_valid": 0.95})], {"path": "/api/alpha/decisions"})
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        missing_age = await card_judge.run(ctx, card_judge.AgentConfig(), _sample_card(age=None))
        non_fictional = await card_judge.run(
            ctx,
            card_judge.AgentConfig(),
            card_judge.CardJudgeInput(
                target_type="character",
                data={"name": "Người thật", "age": 30, "is_fictional": False},
            ),
        )
        public_minor_nsfw = await card_judge.run(
            ctx,
            card_judge.AgentConfig(),
            card_judge.CardJudgeInput(
                target_type="character",
                data={"name": "Vy", "age": 16, "is_fictional": True, "tags": ["nsfw"]},
                visibility="public",
            ),
        )
        empty_world = await card_judge.run(
            ctx,
            card_judge.AgentConfig(),
            VietrpWorld(name="Trống", locations=[]),
        )
    finally:
        await services.aclose()

    for res in (missing_age, non_fictional, public_minor_nsfw, empty_world):
        assert res.value.passed is False
        safety = next(c for c in res.value.criteria if c.id == "safety_valid")
        assert safety.passed is False
        assert safety.probability == 0.0
        assert safety.hint_vi


async def test_card_judge_falls_back_to_chat_when_decisions_alpha_fails() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([{"status": 404, "json": {"error": {"message": "alpha gone"}}}], {"path": "/api/alpha/decisions"})
    fallback_answers = {cid: {"p": 0.85 if cid != "distinct_voice" else 0.4} for cid in card_judge.CRITERIA}
    llm.add(
        [
            {
                "status": 200,
                "json": {
                    "choices": [{"message": {"content": json.dumps(fallback_answers)}}],
                    "usage": {"prompt_tokens": 180, "completion_tokens": 40, "cost": 0.00015},
                },
            }
        ],
        {"path": "/api/v1/chat/completions"},
    )
    gateway, services, recorder, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        res = await card_judge.run(ctx, card_judge.AgentConfig(), _sample_card())
    finally:
        await services.aclose()

    assert res.value.passed is False
    by_id = {c.id: c for c in res.value.criteria}
    assert by_id["distinct_voice"].probability == 0.4 and by_id["distinct_voice"].passed is False
    assert by_id["completeness"].probability == 0.85 and by_id["completeness"].passed is True
    assert len(recorder.calls) == 1
