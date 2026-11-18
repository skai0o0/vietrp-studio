"""Director (architecture section 3, agent 3): approves or rejects a draft, per criterion.

Role-name trap: this is the agent `vietrp-agent` calls "judge". Each criterion is one atomic yes/no Decisions
question. `probability` in the verdict is always the probability that the criterion is satisfied (for "bad when yes"
questions it is 1 - p). The retry loop lives in the turn pipeline (WP-O), not here.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult
from app.agents.orchestrator import split_choice
from app.llm.decisions import Noul, Question, Score
from app.llm.defaults import DEFAULT_MODELS
from app.prompts import render_prompt
from app.schemas.events import DirectorCriterion, DirectorVerdict

AGENT_ID = "director"
USER_LED_KEY = "user_led"
PRIORITY_KEY = "priority"


@dataclass(frozen=True, slots=True)
class CriterionSpec:
    id: str
    # True when answering "yes" is the good outcome.
    good_when_yes: bool


# Architecture section 3, agent 3. Order is the display order.
CRITERIA: tuple[CriterionSpec, ...] = (
    CriterionSpec("answers_last", True),
    CriterionSpec("no_new_events", False),
    CriterionSpec("no_player_voice", False),
    CriterionSpec("no_assistant_voice", False),
)


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["director"]
    # A criterion passes at or above this probability of being satisfied. 0.8 comes from the reference judge, which
    # measured it on 24 Vietnamese samples (vietrp-agent judge.py).
    threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    # Chars of the previous message and draft sent to the model.
    max_chars: int = Field(default=3000, ge=1)


@dataclass(frozen=True, slots=True)
class DirectorInput:
    character_name: str
    user_name: str
    user_message: str
    draft: str
    # 0 for the first draft, then 1, 2, ... for retries.
    attempt: int = 0
    # Criteria ids to mark passed without failing the draft (e.g. continue turns skip answers_last / no_new_events).
    skip_criteria: Collection[str] = ()


class DirectorOutcome(BaseModel):
    verdict: DirectorVerdict
    # 0 routine, 1 notable, 2 pivotal. Stored as `meta.priority` for the Archivist (P4).
    priority: int = Field(default=0, ge=0, le=2)

    @property
    def passed(self) -> bool:
        return self.verdict.passed

    @property
    def score(self) -> float:
        return self.verdict.score


def fix_hints(verdict: DirectorVerdict) -> list[str]:
    """Hints of the failed criteria, ready for `WriterInput.fix_hints`."""
    return [c.hint_vi for c in verdict.criteria if not c.passed and c.hint_vi]


def better(a: DirectorOutcome, b: DirectorOutcome) -> DirectorOutcome:
    """The higher-scoring outcome; a tie keeps `a` (the earlier one)."""
    return b if b.score > a.score else a


def build_questions(inp: DirectorInput) -> dict[str, Question]:
    names = {"char": inp.character_name, "user": inp.user_name}
    questions: dict[str, Question] = {
        spec.id: Noul(instructions=render_prompt(f"director/q_{spec.id}.j2", **names)) for spec in CRITERIA
    }
    questions[USER_LED_KEY] = Noul(instructions=render_prompt("director/q_user_led.j2", **names))
    instructions, criteria = split_choice(render_prompt("director/q_priority.j2", **names))
    questions[PRIORITY_KEY] = Score(criteria=list(criteria), instructions=instructions)
    return questions


async def run(ctx: AgentContext, cfg: AgentConfig, inp: DirectorInput) -> AgentResult[DirectorOutcome]:
    """Raises on LLM failure; the caller decides (the turn pipeline wraps it in `run_non_critical` and keeps the
    draft)."""
    state = {
        "user_message": inp.user_message[: cfg.max_chars],
        "draft": inp.draft[: cfg.max_chars],
    }
    questions = build_questions(inp)
    result = await ctx.llm.decide(AGENT_ID, cfg.model, state, questions)
    user_led = result.noul(USER_LED_KEY) >= cfg.threshold
    skip = set(inp.skip_criteria)
    criteria: list[DirectorCriterion] = []
    for spec in CRITERIA:
        said_yes = result.noul(spec.id)
        good = said_yes if spec.good_when_yes else 1.0 - said_yes
        # New events the player asked for are not the Writer's doing (reference judge.py AUX check).
        if spec.id == "no_new_events" and user_led:
            good = 1.0
        skipped = spec.id in skip
        passed = True if skipped else (good >= cfg.threshold)
        hint = (
            "" if passed else render_prompt(f"director/fix_{spec.id}.j2", char=inp.character_name, user=inp.user_name)
        )
        criteria.append(DirectorCriterion(id=spec.id, probability=round(good, 4), passed=passed, hint_vi=hint))
    active = [c for c in criteria if c.id not in skip]
    score = round(sum(c.probability for c in active) / len(active), 4) if active else 1.0
    verdict = DirectorVerdict(
        passed=all(c.passed for c in criteria), score=score, criteria=criteria, attempt=inp.attempt
    )
    priority_question = questions[PRIORITY_KEY]
    top = len(priority_question.criteria) - 1 if isinstance(priority_question, Score) else 0
    priority = min(top, max(0, round(result.score(PRIORITY_KEY))))
    return AgentResult(value=DirectorOutcome(verdict=verdict, priority=priority), usage=[result.usage])
