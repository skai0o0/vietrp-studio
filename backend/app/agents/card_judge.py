"""Card Judge (architecture section 3, agent 7): scores a card or world across 6 atomic criteria.

Combines Decisions API probabilities with deterministic safety checks (`age` present & non-negative int and
`is_fictional is True` for characters; non-empty name + locations for worlds) and always returns per-criterion
probabilities, pass/fail, and Vietnamese fix hints — never just a single number.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult
from app.formats.card import VietrpCard
from app.formats.world import VietrpWorld
from app.llm.decisions import Noul, Question
from app.llm.defaults import DEFAULT_MODELS
from app.pipeline.safety import ADULT_AGE, is_nsfw_tagged
from app.prompts import render_prompt
from app.schemas.creator import CardJudgeCriterion, CardJudgeResult

AGENT_ID = "card_judge"

# Evaluation criteria in display order (architecture section 3, agent 7).
CRITERIA: tuple[str, ...] = (
    "completeness",
    "atomic_concise",
    "no_command_tone",
    "distinct_voice",
    "actionable_goals",
    "safety_valid",
)


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["card_judge"]
    threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    max_chars: int = Field(default=6000, ge=1)


class CardJudgeInput(BaseModel):
    target_type: Literal["character", "world"]
    data: dict[str, Any]
    visibility: str = "private"


def _normalize_input(inp: CardJudgeInput | VietrpCard | VietrpWorld) -> CardJudgeInput:
    if isinstance(inp, CardJudgeInput):
        return inp
    if isinstance(inp, VietrpCard):
        return CardJudgeInput(target_type="character", data=inp.model_dump(mode="json"))
    return CardJudgeInput(target_type="world", data=inp.model_dump(mode="json"))


def deterministic_safety(
    target_type: Literal["character", "world"], data: Mapping[str, Any], visibility: str
) -> tuple[bool, str]:
    """Check hard safety invariants before trusting model probabilities."""
    if target_type == "character":
        age = data.get("age")
        age_ok = isinstance(age, int) and not isinstance(age, bool) and 0 <= age <= 10000
        fictional_ok = data.get("is_fictional") is True
        raw_tags = data.get("tags")
        tags = [str(tag) for tag in raw_tags] if isinstance(raw_tags, list) else []
        minor_or_unknown = not age_ok or (isinstance(age, int) and age < ADULT_AGE)
        if visibility == "public" and minor_or_unknown and is_nsfw_tagged(tags):
            return False, "minor_nsfw_public"
        if not age_ok:
            return False, "missing_age"
        if not fictional_ok:
            return False, "non_fictional"
        return True, ""

    name = data.get("name")
    locations = data.get("locations")
    has_name = isinstance(name, str) and bool(name.strip())
    has_locations = (
        isinstance(locations, list)
        and len(locations) > 0
        and any(isinstance(loc, Mapping) and str(loc.get("name", "")).strip() for loc in locations)
    )
    if not has_name or not has_locations:
        return False, "world_incomplete"
    return True, ""


def build_questions(target_type: Literal["character", "world"]) -> dict[str, Question]:
    return {
        criterion_id: Noul(instructions=render_prompt(f"card_judge/q_{criterion_id}.j2", target_type=target_type))
        for criterion_id in CRITERIA
    }


def _build_state(inp: CardJudgeInput, max_chars: int) -> dict[str, str]:
    serialized = json.dumps(inp.data, ensure_ascii=False, indent=2)
    return {
        "target_type": inp.target_type,
        "visibility": inp.visibility,
        "content": serialized[:max_chars],
    }


def _hint_for(criterion_id: str, target_type: Literal["character", "world"], *, reason: str = "general") -> str:
    if criterion_id == "safety_valid":
        return render_prompt("card_judge/fix_safety_valid.j2", target_type=target_type, reason=reason)
    return render_prompt(f"card_judge/fix_{criterion_id}.j2", target_type=target_type)


async def run(
    ctx: AgentContext,
    cfg: AgentConfig,
    inp: CardJudgeInput | VietrpCard | VietrpWorld,
) -> AgentResult[CardJudgeResult]:
    """Evaluate a character card or world across the 6 criteria."""
    normalized = _normalize_input(inp)
    target_type = normalized.target_type
    questions = build_questions(target_type)
    state = _build_state(normalized, cfg.max_chars)
    result = await ctx.llm.decide(AGENT_ID, cfg.model, state, questions)
    det_ok, det_reason = deterministic_safety(target_type, normalized.data, normalized.visibility)

    criteria: list[CardJudgeCriterion] = []
    for criterion_id in CRITERIA:
        label = render_prompt(f"card_judge/label_{criterion_id}.j2", target_type=target_type)
        raw_prob = result.noul(criterion_id)
        probability = round(min(1.0, max(0.0, raw_prob)), 4)

        if criterion_id == "safety_valid" and not det_ok:
            probability = 0.0
            passed = False
            hint_vi = _hint_for(criterion_id, target_type, reason=det_reason)
        else:
            passed = probability >= cfg.threshold
            hint_vi = "" if passed else _hint_for(criterion_id, target_type)

        criteria.append(
            CardJudgeCriterion(
                id=criterion_id,
                label=label,
                probability=probability,
                passed=passed,
                hint_vi=hint_vi,
            )
        )

    score = round(sum(c.probability for c in criteria) / len(criteria), 4)
    overall_passed = all(c.passed for c in criteria) and score >= cfg.threshold
    return AgentResult(
        value=CardJudgeResult(
            passed=overall_passed,
            score=score,
            threshold=cfg.threshold,
            criteria=criteria,
        ),
        usage=[result.usage],
    )


__all__ = [
    "AGENT_ID",
    "CRITERIA",
    "AgentConfig",
    "CardJudgeCriterion",
    "CardJudgeInput",
    "CardJudgeResult",
    "build_questions",
    "deterministic_safety",
    "run",
]
