"""Writer (architecture section 3, agent 2): streams one speaker's draft from an `AssembledPrompt`."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.agents.base import AgentContext
from app.core.config import WRITER_REASONING_EXTRA_TOKENS
from app.llm.chat import ChatParams, ContentDelta, Finish, ReasoningDelta
from app.llm.defaults import DEFAULT_MODELS
from app.llm.usage import Usage
from app.pipeline.prompt_assembler import AssembledPrompt
from app.prompts import render_prompt

AGENT_ID = "writer"
PREFILL_LAYER = "prefill"


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["writer"]
    # Sampling defaults mirror `ChatParams`; the per-user preset may override them later.
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    max_tokens: int = Field(default=1500, ge=1)
    reasoning: str = "off"


@dataclass(frozen=True, slots=True)
class WriterInput:
    prompt: AssembledPrompt
    # Director hints from a rejected attempt (Vietnamese). Empty on the first attempt.
    fix_hints: Sequence[str] = ()
    # The rejected draft, shown to the model next to the hints.
    rejected_draft: str | None = None


class WriterDelta(BaseModel):
    text: str


class WriterReasoning(BaseModel):
    text: str


class WriterDone(BaseModel):
    """Last item of a completed stream. A stream closed early (stop) never yields it: keep the deltas."""

    text: str
    finish_reason: str = ""
    usage: Usage | None = None
    reasoning: str = ""


def config_for(model: str, reasoning: str) -> AgentConfig:
    """Writer config for a chat: reasoning tokens share max_tokens, so the budget grows when reasoning is on."""
    base = AgentConfig(model=model, reasoning=reasoning)
    if reasoning != "off":
        base.max_tokens += WRITER_REASONING_EXTRA_TOKENS
    return base


def build_messages(inp: WriterInput) -> list[dict[str, Any]]:
    """The assembled messages, plus a user-role fix message before the prefill (never another system layer, so the
    minor-safety rule stays the last system layer)."""
    messages: list[dict[str, Any]] = [dict(m) for m in inp.prompt.messages]
    if not inp.fix_hints:
        return messages
    fix = {
        "role": "user",
        "content": render_prompt("writer/fix_hints.j2", hints=list(inp.fix_hints), rejected_draft=inp.rejected_draft),
    }
    has_prefill = bool(inp.prompt.layers) and inp.prompt.layers[-1].name == PREFILL_LAYER
    messages.insert(len(messages) - 1 if has_prefill else len(messages), fix)
    return messages


async def run(
    ctx: AgentContext, cfg: AgentConfig, inp: WriterInput
) -> AsyncIterator[WriterDelta | WriterReasoning | WriterDone]:
    """Stream the draft. Closing the iterator early cancels the upstream stream and still records usage."""
    params = ChatParams(
        temperature=cfg.temperature, top_p=cfg.top_p, max_tokens=cfg.max_tokens, reasoning=cfg.reasoning
    )
    parts: list[str] = []
    thoughts: list[str] = []
    reason = ""
    usage: Usage | None = None
    stream = ctx.llm.stream(AGENT_ID, cfg.model, build_messages(inp), params)
    try:
        async for event in stream:
            if isinstance(event, ContentDelta):
                parts.append(event.text)
                yield WriterDelta(text=event.text)
            elif isinstance(event, ReasoningDelta):
                thoughts.append(event.text)
                yield WriterReasoning(text=event.text)
            elif isinstance(event, Finish):
                reason = event.reason
            elif isinstance(event, Usage):
                usage = event
    finally:
        await stream.aclose()  # type: ignore[attr-defined]
    yield WriterDone(text="".join(parts), finish_reason=reason, usage=usage, reasoning="".join(thoughts))
