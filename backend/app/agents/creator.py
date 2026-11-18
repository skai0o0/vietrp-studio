"""Creator (architecture section 3 agent 6 & section 5.4): conversational interview and 2-step generation."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.base import AgentContext, AgentResult
from app.creator import card_defaults, world_defaults
from app.formats.card import VietrpCard
from app.formats.common import CURRENT_SPEC_VERSION, FormatWarning, normalize_tag
from app.formats.validate import validate_card, validate_world
from app.formats.world import LEVEL_ORDER, VietrpWorld
from app.llm.chat import ChatMessage, ChatParams, ContentDelta, Finish
from app.llm.client import LLMError
from app.llm.defaults import DEFAULT_MODELS
from app.llm.usage import Usage
from app.pipeline import safety
from app.pipeline.world_turn import slugify_name
from app.prompts import render_prompt

AGENT_ID = "creator"
TargetType = Literal["character", "world"]

_LEVEL_RANK = {level: idx for idx, level in enumerate(LEVEL_ORDER)}
_AGE_STR_RE = re.compile(r"^\s*(\d{1,4})(?:\s*tuổi)?\s*$", re.IGNORECASE)
_FENCE_RE = re.compile(r"^```(?:json|[a-zA-Z0-9_-]+)?\s*\n?(.*?)\n?```\s*$", re.DOTALL)

_CARD_NAME_MAX = 80
_TAGLINE_MAX = 140
_TAG_MAX_LEN = 32
_TAGS_MAX = 20
_AGE_MAX = 10000
_TENSION_MAX = 4


class AgentConfig(BaseModel):
    model: str = DEFAULT_MODELS["creator"]
    temperature: float = Field(default=0.85, ge=0.0, le=2.0)
    format_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4000, ge=1)


class CreatorDelta(BaseModel):
    text: str


class CreatorDone(BaseModel):
    text: str
    finish_reason: str = ""
    usage: Usage | None = None


def build_interview_messages(
    *,
    target_type: TargetType,
    seed: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    user_message: str,
) -> list[ChatMessage]:
    system = render_prompt("creator/chat_interview.j2", target_type=target_type, seed=dict(seed))
    out: list[ChatMessage] = [
        {"role": "system", "content": system},
        {"role": "system", "content": safety.creator_rule()},
    ]
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            out.append({"role": role, "content": content})
    if user_message.strip():
        out.append({"role": "user", "content": user_message})
    return out


async def interview_reply(
    ctx: AgentContext,
    cfg: AgentConfig,
    *,
    target_type: TargetType,
    seed: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    user_message: str,
) -> AgentResult[str]:
    """Non-streaming conversational interview reply."""
    chat_messages = build_interview_messages(
        target_type=target_type,
        seed=seed,
        messages=messages,
        user_message=user_message,
    )
    params = ChatParams(temperature=cfg.temperature, max_tokens=cfg.max_tokens, reasoning="off")
    text, usage = await ctx.llm.complete(AGENT_ID, cfg.model, chat_messages, params)
    return AgentResult(value=text.strip(), usage=[usage])


async def interview_stream(
    ctx: AgentContext,
    cfg: AgentConfig,
    *,
    target_type: TargetType,
    seed: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    user_message: str,
) -> AsyncIterator[CreatorDelta | CreatorDone]:
    """Streaming conversational interview reply."""
    chat_messages = build_interview_messages(
        target_type=target_type,
        seed=seed,
        messages=messages,
        user_message=user_message,
    )
    params = ChatParams(temperature=cfg.temperature, max_tokens=cfg.max_tokens, reasoning="off")
    parts: list[str] = []
    reason = ""
    usage: Usage | None = None
    stream = ctx.llm.stream(AGENT_ID, cfg.model, chat_messages, params)
    try:
        async for event in stream:
            if isinstance(event, ContentDelta):
                parts.append(event.text)
                yield CreatorDelta(text=event.text)
            elif isinstance(event, Finish):
                reason = event.reason
            elif isinstance(event, Usage):
                usage = event
    finally:
        await stream.aclose()  # type: ignore[attr-defined]
    yield CreatorDone(text="".join(parts).strip(), finish_reason=reason, usage=usage)


async def draft_raw(
    ctx: AgentContext,
    cfg: AgentConfig,
    *,
    target_type: TargetType,
    seed: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
) -> AgentResult[str]:
    """Step 1: free-form Vietnamese prose profile faithful to seed and chat history."""
    system_template = "creator/draft_raw_card.j2" if target_type == "character" else "creator/draft_raw_world.j2"
    system = render_prompt(system_template)
    user = render_prompt(
        "creator/draft_raw_user.j2",
        target_type=target_type,
        seed=dict(seed),
        messages=[dict(m) for m in messages],
    )
    chat_messages: list[ChatMessage] = [
        {"role": "system", "content": system},
        {"role": "system", "content": safety.creator_rule()},
        {"role": "user", "content": user},
    ]
    params = ChatParams(temperature=cfg.temperature, max_tokens=cfg.max_tokens, reasoning="off")
    text, usage = await ctx.llm.complete(AGENT_ID, cfg.model, chat_messages, params)
    return AgentResult(value=text.strip(), usage=[usage])


def extract_json_object(text: str) -> dict[str, Any]:
    """Strip markdown fences / prose wrappers and parse a JSON object."""
    cleaned = text.strip()
    fence_match = _FENCE_RE.match(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed = None
        for idx, ch in enumerate(cleaned):
            if ch != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(cleaned, idx)
                if isinstance(candidate, dict):
                    parsed = candidate
                    break
            except json.JSONDecodeError:
                continue
        if not isinstance(parsed, dict):
            raise LLMError("llm_bad_response", None, "Creator formatted output is not valid JSON") from None

    if not isinstance(parsed, dict):
        raise LLMError("llm_bad_response", None, "Creator formatted output must be a JSON object")
    return parsed


def _unique_slug(base_text: str, used: set[str], fallback: str) -> str:
    base = slugify_name(base_text, fallback)
    candidate = base
    counter = 2
    while candidate in used:
        suffix = f"_{counter}"
        candidate = f"{base[: 40 - len(suffix)]}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def _str(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if isinstance(item, str | int | float) and str(item).strip()]


def _clean_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = normalize_tag(item).lower()[:_TAG_MAX_LEN].strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
            if len(out) >= _TAGS_MAX:
                break
    return out


def _parse_age(raw_age: Any, seed: Mapping[str, Any] | None) -> int | None:
    """Parse an explicit integer age when unambiguous; never invent an age."""
    for candidate in (raw_age, seed.get("age") if seed else None):
        if isinstance(candidate, int) and not isinstance(candidate, bool) and 0 <= candidate <= _AGE_MAX:
            return candidate
        if isinstance(candidate, float) and candidate.is_integer() and 0 <= int(candidate) <= _AGE_MAX:
            return int(candidate)
        if isinstance(candidate, str):
            match = _AGE_STR_RE.match(candidate)
            if match:
                parsed = int(match.group(1))
                if 0 <= parsed <= _AGE_MAX:
                    return parsed
    return None


def _slug_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, Mapping):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            out[slugify_name(k, "char")] = v.strip()
    return out


def repair_card_dict(raw: Mapping[str, Any], seed: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Repair minimal missing wrapper defaults and normalize slugs/tags on a `vietrp-card` dict."""
    source: Mapping[str, Any] = raw
    if "name" not in source and isinstance(source.get("data"), Mapping):
        source = source["data"]

    out = card_defaults()
    for key in VietrpCard.model_fields:
        if key in source and source[key] is not None:
            out[key] = source[key]

    out["format"] = "vietrp-card"
    out["spec_version"] = CURRENT_SPEC_VERSION
    if "is_fictional" not in source or source.get("is_fictional") is None:
        out["is_fictional"] = True
    out["age"] = _parse_age(source.get("age"), seed)

    name = _str(out.get("name"))[:_CARD_NAME_MAX]
    if not name and seed:
        name = _str(seed.get("name"))[:_CARD_NAME_MAX]
    out["name"] = name
    out["aliases"] = _str_list(out.get("aliases"))
    out["tagline"] = _str(out.get("tagline"))[:_TAGLINE_MAX]
    for field in ("appearance", "personality", "backstory", "goals"):
        out[field] = _str(out.get(field))
    out["limits"] = _str_list(out.get("limits"))
    out["tags"] = _clean_tags(out.get("tags"))
    out["lorebook_ids"] = list(out.get("lorebook_ids") or [])

    greetings = _str_list(out.get("greetings"))
    if not greetings and isinstance(source.get("first_mes"), str) and source["first_mes"].strip():
        greetings = [source["first_mes"].strip()]
    out["greetings"] = greetings

    # Secrets with unique slug ids.
    used_secrets: set[str] = set()
    secrets: list[dict[str, str]] = []
    for item in source.get("secrets") or [] if isinstance(source.get("secrets"), list) else []:
        if isinstance(item, str) and item.strip():
            secrets.append(
                {
                    "id": _unique_slug(item, used_secrets, "secret"),
                    "content": item.strip(),
                    "reveal_when": "",
                }
            )
        elif isinstance(item, Mapping):
            content = _str(item.get("content"))
            if not content:
                continue
            raw_id = _str(item.get("id")) or content
            secrets.append(
                {
                    "id": _unique_slug(raw_id, used_secrets, "secret"),
                    "content": content,
                    "reveal_when": _str(item.get("reveal_when")),
                }
            )
    out["secrets"] = secrets

    raw_speech = source.get("speech")
    speech = raw_speech if isinstance(raw_speech, Mapping) else {}
    out["speech"] = {
        "style": _str(speech.get("style")),
        "catchphrases": _str_list(speech.get("catchphrases")),
        "examples": _str_list(speech.get("examples")),
    }

    raw_addr = source.get("addressing")
    addr = raw_addr if isinstance(raw_addr, Mapping) else {}
    out["addressing"] = {
        "default": _str(addr.get("default")),
        "user": _str(addr.get("user")),
        "by_character": _slug_map(addr.get("by_character")),
    }

    raw_rel = source.get("relationships")
    rel = raw_rel if isinstance(raw_rel, Mapping) else {}
    out["relationships"] = {
        "user": _str(rel.get("user")),
        "by_character": _slug_map(rel.get("by_character")),
    }

    out["extras"] = _slug_map(source.get("extras"))
    return out


def _repair_world_locations(raw_locations: Any) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    if not isinstance(raw_locations, list):
        return [], {}, {}

    used_ids: set[str] = set()
    id_map: dict[str, str] = {}
    name_map: dict[str, str] = {}
    staged: list[dict[str, Any]] = []

    for item in raw_locations:
        if not isinstance(item, Mapping):
            continue
        loc_name = _str(item.get("name"))
        raw_id = _str(item.get("id"))
        if not loc_name and not raw_id:
            continue
        slug = _unique_slug(raw_id or loc_name, used_ids, "place")
        if raw_id:
            id_map[raw_id] = slug
            id_map[slugify_name(raw_id, "place")] = slug
        if loc_name:
            name_map.setdefault(loc_name.lower(), slug)
        raw_level = _str(item.get("level")).lower()
        level = raw_level if raw_level in _LEVEL_RANK else "place"
        staged.append(
            {
                "id": slug,
                "_raw_parent": _str(item.get("parent_id")),
                "level": level,
                "name": loc_name or slug,
                "description": _str(item.get("description")),
            }
        )

    by_id = {loc["id"]: loc for loc in staged}
    for loc in staged:
        raw_parent = loc.pop("_raw_parent")
        parent_id: str | None = None
        if raw_parent:
            parent_id = (
                id_map.get(raw_parent)
                or id_map.get(slugify_name(raw_parent, "place"))
                or name_map.get(raw_parent.lower())
            )
        if parent_id == loc["id"] or parent_id not in by_id:
            parent_id = None
        loc["parent_id"] = parent_id

    # Repair parent/child level ordering and guard against cycles.
    for loc in staged:
        pid = loc["parent_id"]
        if pid is None:
            continue
        parent = by_id[pid]
        if _LEVEL_RANK[loc["level"]] <= _LEVEL_RANK[parent["level"]]:
            parent_rank = _LEVEL_RANK[parent["level"]]
            if parent_rank + 1 < len(LEVEL_ORDER):
                loc["level"] = LEVEL_ORDER[parent_rank + 1]
            else:
                loc["parent_id"] = None

    for loc in staged:
        seen: set[str] = set()
        curr: dict[str, Any] | None = loc
        while curr is not None and curr["parent_id"] is not None:
            if curr["id"] in seen:
                loc["parent_id"] = None
                break
            seen.add(curr["id"])
            curr = by_id.get(curr["parent_id"])

    return staged, id_map, name_map


def repair_world_dict(raw: Mapping[str, Any], seed: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Repair minimal missing wrapper defaults and normalize tree slugs on a `vietrp-world` dict."""
    source: Mapping[str, Any] = raw
    if "name" not in source and isinstance(source.get("data"), Mapping):
        source = source["data"]

    out = world_defaults()
    for key in VietrpWorld.model_fields:
        if key in source and source[key] is not None:
            out[key] = source[key]

    out["format"] = "vietrp-world"
    out["spec_version"] = CURRENT_SPEC_VERSION
    name = _str(out.get("name"))[:_CARD_NAME_MAX]
    if not name and seed:
        name = _str(seed.get("name"))[:_CARD_NAME_MAX]
    out["name"] = name
    out["rules"] = _str(out.get("rules"))
    out["tags"] = _clean_tags(out.get("tags"))
    out["lorebook_ids"] = list(out.get("lorebook_ids") or [])

    locations, id_map, name_map = _repair_world_locations(source.get("locations"))
    out["locations"] = locations
    valid_loc_ids = {loc["id"] for loc in locations}

    used_openings: set[str] = set()
    openings: list[dict[str, Any]] = []
    for item in source.get("openings") or [] if isinstance(source.get("openings"), list) else []:
        if not isinstance(item, Mapping):
            continue
        title = _str(item.get("title"))
        raw_id = _str(item.get("id"))
        slug = _unique_slug(raw_id or title, used_openings, "opening")
        raw_loc = _str(item.get("location_id"))
        loc_id = id_map.get(raw_loc) or id_map.get(slugify_name(raw_loc, "place")) or name_map.get(raw_loc.lower())
        if loc_id not in valid_loc_ids:
            loc_id = locations[-1]["id"] if locations else slugify_name(raw_loc, "place")
        raw_tension = item.get("tension", 0)
        tension_num = raw_tension if isinstance(raw_tension, int | float) and not isinstance(raw_tension, bool) else 0
        tension = min(_TENSION_MAX, max(0, round(tension_num)))
        present_raw = item.get("present_ids")
        present_ids = [
            slugify_name(str(p), "char")
            for p in (present_raw if isinstance(present_raw, list) else [])
            if isinstance(p, str) and p.strip()
        ]
        openings.append(
            {
                "id": slug,
                "title": title,
                "message": _str(item.get("message")),
                "time": _str(item.get("time")),
                "location_id": loc_id,
                "present_ids": present_ids,
                "tension": tension,
                "player_role": _str(item.get("player_role")),
            }
        )
    out["openings"] = openings
    return out


async def format_json(
    ctx: AgentContext,
    cfg: AgentConfig,
    *,
    target_type: TargetType,
    raw_draft: str,
    seed: Mapping[str, Any],
) -> tuple[dict[str, Any], list[FormatWarning], Usage]:
    """Step 2: convert raw Vietnamese draft to validated `vietrp-card` or `vietrp-world` JSON."""
    system_template = "creator/format_card.j2" if target_type == "character" else "creator/format_world.j2"
    system = render_prompt(system_template)
    user = render_prompt("creator/format_user.j2", target_type=target_type, seed=dict(seed), raw_draft=raw_draft)
    chat_messages: list[ChatMessage] = [
        {"role": "system", "content": system},
        {"role": "system", "content": safety.creator_rule()},
        {"role": "user", "content": user},
    ]
    params = ChatParams(temperature=cfg.format_temperature, max_tokens=cfg.max_tokens, reasoning="off")
    text, usage = await ctx.llm.complete(AGENT_ID, cfg.model, chat_messages, params)

    parsed = extract_json_object(text)
    if target_type == "character":
        repaired = repair_card_dict(parsed, seed)
        card, warnings = validate_card(repaired, allow_missing_age=True)
        return card.model_dump(mode="json"), warnings, usage

    repaired = repair_world_dict(parsed, seed)
    world, warnings = validate_world(repaired)
    return world.model_dump(mode="json"), warnings, usage


__all__ = [
    "AGENT_ID",
    "AgentConfig",
    "CreatorDelta",
    "CreatorDone",
    "TargetType",
    "build_interview_messages",
    "draft_raw",
    "extract_json_object",
    "format_json",
    "interview_reply",
    "interview_stream",
    "repair_card_dict",
    "repair_world_dict",
]
