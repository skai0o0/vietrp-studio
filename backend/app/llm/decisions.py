"""Decisions: many atomic classification questions in one call (OpenRouter alpha API, with a chat fallback)."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.llm.chat import ChatParams, complete_chat
from app.llm.client import LLMError, OpenRouterClient
from app.llm.defaults import FALLBACK_CHAT_MODEL
from app.llm.templating import render
from app.llm.usage import Usage, UsageContext, UsageRecorder, record_usage

logger = logging.getLogger(__name__)

DECISIONS_PATH = "/api/alpha/decisions"


class QuestionBudgetExceeded(LLMError):
    """Raised before any network call when a request carries more questions than the budget allows."""

    def __init__(self, count: int, limit: int) -> None:
        super().__init__("decisions_budget_exceeded", None, f"{count} questions exceed the budget of {limit}")
        self.count = count
        self.limit = limit


# --- Questions ---------------------------------------------------------------------------------


class Choice(BaseModel):
    type: Literal["choice"] = "choice"
    # option key -> short description of the option
    criteria: dict[str, str]
    instructions: str


class Noul(BaseModel):
    """A yes/no question answered with a probability."""

    type: Literal["noul"] = "noul"
    instructions: str


class Score(BaseModel):
    """An ordered scale; the answer is a number from 0 to len(criteria) - 1."""

    type: Literal["score"] = "score"
    criteria: list[str]
    instructions: str


Question = Choice | Noul | Score


# --- Answers -----------------------------------------------------------------------------------


class ChoiceAnswer(BaseModel):
    kind: Literal["choice"] = "choice"
    choice: str
    confidence: float
    probabilities: dict[str, float]


class NoulAnswer(BaseModel):
    kind: Literal["noul"] = "noul"
    p: float


class ScoreAnswer(BaseModel):
    kind: Literal["score"] = "score"
    score: float


Answer = Annotated[ChoiceAnswer | NoulAnswer | ScoreAnswer, Field(discriminator="kind")]


class DecisionResult(BaseModel):
    answers: dict[str, Answer]
    usage: Usage
    model: str
    used_fallback: bool = False

    def choice(self, key: str) -> ChoiceAnswer:
        answer = self.answers[key]
        if not isinstance(answer, ChoiceAnswer):
            raise TypeError(f"answer {key!r} is not a choice")
        return answer

    def noul(self, key: str) -> float:
        answer = self.answers[key]
        if not isinstance(answer, NoulAnswer):
            raise TypeError(f"answer {key!r} is not a noul")
        return answer.p

    def score(self, key: str) -> float:
        answer = self.answers[key]
        if not isinstance(answer, ScoreAnswer):
            raise TypeError(f"answer {key!r} is not a score")
        return answer.score


class DecisionClient(Protocol):
    async def decide(
        self,
        api_key: str,
        model: str,
        state: dict[str, str],
        questions: dict[str, Question],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> DecisionResult: ...


def check_budget(questions: dict[str, Question], limit: int) -> None:
    if len(questions) > limit:
        raise QuestionBudgetExceeded(len(questions), limit)


def _bad(message: str) -> LLMError:
    return LLMError("llm_bad_response", None, message)


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _bad(f"{what} is not a number")
    return float(value)


def normalize_choice(raw: dict[str, Any], key: str) -> ChoiceAnswer:
    choice = raw.get("choice")
    if not isinstance(choice, str):
        raise _bad(f"answer {key!r} has no choice")
    probs_raw = raw.get("probabilities") or {}
    if not isinstance(probs_raw, dict):
        raise _bad(f"answer {key!r} has malformed probabilities")
    probs = {str(k): _number(v, f"probability {k!r}") for k, v in probs_raw.items()}
    confidence = _number(raw["confidence"], f"confidence of {key!r}") if "confidence" in raw else probs.get(choice, 0.0)
    return ChoiceAnswer(choice=choice, confidence=confidence, probabilities=probs)


def normalize_answers(raw_answers: Any, questions: dict[str, Question]) -> dict[str, Answer]:
    """Turn the alpha API's `answers` object into typed answers; every asked question must be answered."""
    if not isinstance(raw_answers, dict):
        raise _bad("response has no answers object")
    out: dict[str, Answer] = {}
    for key, question in questions.items():
        raw = raw_answers.get(key)
        if not isinstance(raw, dict):
            raise _bad(f"missing answer for {key!r}")
        if isinstance(question, Choice):
            out[key] = normalize_choice(raw, key)
        elif isinstance(question, Noul):
            out[key] = NoulAnswer(p=_number(raw.get("noul"), f"noul of {key!r}"))
        else:
            out[key] = ScoreAnswer(score=_number(raw.get("score"), f"score of {key!r}"))
    return out


class OpenRouterDecisionClient:
    """Posts to `/api/alpha/decisions`. Alpha API: shape may change, so parsing is strict and raises."""

    def __init__(self, client: OpenRouterClient) -> None:
        self._client = client

    async def decide(
        self,
        api_key: str,
        model: str,
        state: dict[str, str],
        questions: dict[str, Question],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> DecisionResult:
        check_budget(questions, self._client.cfg.max_questions)
        if recorder is not None and context is None:
            raise ValueError("a usage recorder needs a UsageContext")
        body = {
            "model": model,
            "state": state,
            "questions": {key: q.model_dump() for key, q in questions.items()},
        }
        data = await self._client.post_json(DECISIONS_PATH, api_key, body)
        if not isinstance(data, dict):
            raise _bad("response is not an object")
        usage = Usage.from_api(data.get("usage"))
        # The call is billed even when the body turns out to be unusable, so record before normalizing.
        await record_usage(recorder, context, model, usage)
        answers = normalize_answers(data.get("answers"), questions)
        returned_model = data.get("model")
        return DecisionResult(
            answers=answers, usage=usage, model=returned_model if isinstance(returned_model, str) else model
        )


# --- Chat fallback -----------------------------------------------------------------------------


def build_decision_schema(questions: dict[str, Question]) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for key, q in questions.items():
        if isinstance(q, Choice):
            probs = {opt: {"type": "number"} for opt in q.criteria}
            props[key] = {
                "type": "object",
                "properties": {
                    "probabilities": {
                        "type": "object",
                        "properties": probs,
                        "required": list(probs),
                        "additionalProperties": False,
                    }
                },
                "required": ["probabilities"],
                "additionalProperties": False,
            }
        elif isinstance(q, Noul):
            props[key] = {
                "type": "object",
                "properties": {"p": {"type": "number"}},
                "required": ["p"],
                "additionalProperties": False,
            }
        else:
            props[key] = {
                "type": "object",
                "properties": {"score": {"type": "number"}},
                "required": ["score"],
                "additionalProperties": False,
            }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a model reply that should be a JSON object, tolerating a markdown fence around it."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise _bad("fallback reply is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise _bad("fallback reply is not a JSON object")
    return parsed


def normalize_fallback(parsed: dict[str, Any], questions: dict[str, Question]) -> dict[str, Answer]:
    out: dict[str, Answer] = {}
    for key, q in questions.items():
        raw = parsed.get(key)
        if not isinstance(raw, dict):
            raise _bad(f"fallback reply is missing {key!r}")
        if isinstance(q, Choice):
            probs_raw = raw.get("probabilities")
            if not isinstance(probs_raw, dict):
                raise _bad(f"fallback answer {key!r} has no probabilities")
            probs = {opt: max(0.0, _number(probs_raw.get(opt, 0.0), f"probability {opt!r}")) for opt in q.criteria}
            total = sum(probs.values())
            if total <= 0:
                raise _bad(f"fallback answer {key!r} has all-zero probabilities")
            probs = {opt: p / total for opt, p in probs.items()}
            best = max(probs, key=lambda opt: probs[opt])
            out[key] = ChoiceAnswer(choice=best, confidence=probs[best], probabilities=probs)
        elif isinstance(q, Noul):
            out[key] = NoulAnswer(p=min(1.0, max(0.0, _number(raw.get("p"), f"p of {key!r}"))))
        else:
            top = max(len(q.criteria) - 1, 0)
            out[key] = ScoreAnswer(score=min(float(top), max(0.0, _number(raw.get("score"), f"score of {key!r}"))))
    return out


class ChatFallbackDecisionClient:
    """Answers the same questions with a plain chat model and a strict JSON schema."""

    def __init__(self, client: OpenRouterClient, chat_model: str = FALLBACK_CHAT_MODEL) -> None:
        self._client = client
        self._chat_model = chat_model

    async def decide(
        self,
        api_key: str,
        model: str,
        state: dict[str, str],
        questions: dict[str, Question],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> DecisionResult:
        # `model` is the decision model the caller asked for; a chat model answers in its place.
        check_budget(questions, self._client.cfg.max_questions)
        cfg = self._client.cfg
        prompt = render(
            "decisions_fallback.j2", state=state, questions={k: q.model_dump() for k, q in questions.items()}
        )
        params = ChatParams(
            temperature=cfg.fallback_temperature,
            max_tokens=cfg.fallback_max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "decisions", "strict": True, "schema": build_decision_schema(questions)},
            },
        )
        text, usage = await complete_chat(
            self._client,
            api_key,
            self._chat_model,
            [{"role": "user", "content": prompt}],
            params,
            recorder=recorder,
            context=context,
        )
        answers = normalize_fallback(parse_json_object(text), questions)
        return DecisionResult(answers=answers, usage=usage, model=self._chat_model, used_fallback=True)


def should_fall_back(error: LLMError) -> bool:
    """The alpha API is gone (404/410), broken (5xx after retries), timing out, or returned garbage."""
    if error.code in ("llm_bad_response", "llm_timeout"):
        return True
    return error.status is not None and (error.status in (404, 410) or error.status >= 500)


class ResilientDecisionClient:
    def __init__(self, primary: DecisionClient, fallback: DecisionClient) -> None:
        self._primary = primary
        self._fallback = fallback

    async def decide(
        self,
        api_key: str,
        model: str,
        state: dict[str, str],
        questions: dict[str, Question],
        *,
        recorder: UsageRecorder | None = None,
        context: UsageContext | None = None,
    ) -> DecisionResult:
        try:
            return await self._primary.decide(api_key, model, state, questions, recorder=recorder, context=context)
        except QuestionBudgetExceeded:
            raise
        except LLMError as exc:
            if not should_fall_back(exc):
                raise
            logger.warning("decisions primary failed (%s); using chat fallback", exc.code)
        result = await self._fallback.decide(api_key, model, state, questions, recorder=recorder, context=context)
        return result.model_copy(update={"used_fallback": True})
