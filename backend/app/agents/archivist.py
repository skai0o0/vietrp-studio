"""Archivist (architecture section 3, agent 5): compresses older turns into summary + memorable events.

Ported from `vietrp-agent/backend/vietrp/engine/group.py` (`summary_messages` and `parse_archivist`) into an
async typed agent using Jinja2 templates under `app/prompts/archivist/`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult
from app.core.config import MAX_EVENTS
from app.llm.chat import ChatMessage, ChatParams
from app.llm.defaults import DEFAULT_MODELS
from app.prompts import render_prompt

AGENT_ID = "archivist"
_BULLET_PREFIX_RE = re.compile(r"^(?:[-*•]+|\d+[.)])\s*")
_HEADER_PREFIX_RE = re.compile(r"^[*#\s]+")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SLUG_MAX_LEN = 37  # `sk_` (3) + 37 <= 40 chars


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["archivist"]
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1400, ge=1)
    max_events: int = Field(default=MAX_EVENTS, ge=1)


class MemorableEvent(BaseModel):
    id: str
    title: str
    content: str


class ArchivistMessage(BaseModel):
    seq: int
    speaker_name: str
    content: str
    priority: int = 0


@dataclass(frozen=True, slots=True)
class ArchivistInput:
    messages: Sequence[ArchivistMessage]
    previous_summary: str = ""
    previous_events: Sequence[MemorableEvent] = ()


class ArchivistOutput(BaseModel):
    summary: str
    upto_seq: int
    events: list[MemorableEvent]
    events_added: int


def event_slug(title: str) -> str:
    """NFD ASCII normalize + lowercase + underscore, prefixed with `sk_`."""
    normalized = unicodedata.normalize("NFC", title).strip().lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", normalized)
    ascii_only = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    slug = _NON_SLUG_RE.sub("_", ascii_only).strip("_")[:_SLUG_MAX_LEN].strip("_")
    return f"sk_{slug or 'event'}"


def _is_section_header(line: str, prefix: str) -> tuple[bool, str]:
    cleaned = _HEADER_PREFIX_RE.sub("", line).strip()
    head, sep, tail = cleaned.partition(":")
    normalized_head = head.strip("*# ").upper()
    if normalized_head == prefix:
        return True, tail.strip("*# ").strip() if sep else ""
    return False, ""


def parse_archivist(
    text: str,
    *,
    previous_events: Sequence[MemorableEvent] = (),
    max_events: int = MAX_EVENTS,
) -> tuple[str, list[MemorableEvent], int]:
    """Parse `TÓM TẮT:` and `SỰ KIỆN ĐÁNG NHỚ:` sections; falls back to summary-only when headers are omitted."""
    normalized = unicodedata.normalize("NFC", text or "")
    summary_lines: list[str] = []
    parsed_events: list[MemorableEvent] = []
    part = "summary"

    for raw in normalized.splitlines():
        line = raw.strip()
        if not line:
            continue
        is_sum, sum_tail = _is_section_header(line, "TÓM TẮT")
        if is_sum:
            part = "summary"
            if sum_tail:
                summary_lines.append(sum_tail)
            continue
        is_ev, ev_tail = _is_section_header(line, "SỰ KIỆN ĐÁNG NHỚ")
        if not is_ev:
            is_ev, ev_tail = _is_section_header(line, "SỰ KIỆN")
        if is_ev:
            part = "events"
            line = ev_tail
            if not line:
                continue

        if part == "events":
            body = _BULLET_PREFIX_RE.sub("", line).strip()
            title, sep, content = body.partition("|")
            if not sep:
                title, sep, content = body.partition(":")
            title = title.strip(" -*")
            content = content.strip()
            if title and content:
                parsed_events.append(MemorableEvent(id=event_slug(title), title=title, content=content))
        else:
            summary_lines.append(line)

    seen: set[str] = set()
    unique_events: list[MemorableEvent] = []
    for event in parsed_events:
        if event.id not in seen:
            seen.add(event.id)
            unique_events.append(event)
    capped = unique_events[: max(0, max_events)]

    prev_by_id = {
        ev.id: (unicodedata.normalize("NFC", ev.title.strip()), unicodedata.normalize("NFC", ev.content.strip()))
        for ev in previous_events
    }
    events_added = sum(1 for ev in capped if prev_by_id.get(ev.id) != (ev.title, ev.content))
    return "\n".join(summary_lines).strip(), capped, events_added


async def run(ctx: AgentContext, cfg: AgentConfig, inp: ArchivistInput) -> AgentResult[ArchivistOutput]:
    """Compress `inp.messages` together with prior memory into a summary and memorable events."""
    ordered = sorted(inp.messages, key=lambda m: m.seq)
    if not ordered:
        return AgentResult(
            value=ArchivistOutput(
                summary=inp.previous_summary.strip(),
                upto_seq=0,
                events=list(inp.previous_events),
                events_added=0,
            )
        )

    system = render_prompt("archivist/system.j2")
    user = render_prompt(
        "archivist/user.j2",
        previous_summary=inp.previous_summary.strip(),
        previous_events=list(inp.previous_events),
        messages=ordered,
        max_events=cfg.max_events,
    )
    messages: list[ChatMessage] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    params = ChatParams(temperature=cfg.temperature, max_tokens=cfg.max_tokens, reasoning="off")
    text, usage = await ctx.llm.complete(AGENT_ID, cfg.model, messages, params)
    summary, events, events_added = parse_archivist(
        text, previous_events=inp.previous_events, max_events=cfg.max_events
    )
    if not summary and inp.previous_summary.strip():
        summary = inp.previous_summary.strip()
    upto_seq = ordered[-1].seq + 1
    return AgentResult(
        value=ArchivistOutput(summary=summary, upto_seq=upto_seq, events=events, events_added=events_added),
        usage=[usage],
    )
