"""Shared memory compression, token calibration, and bond refresh helpers (architecture section 5.3).

Used by `single_turn.py`, `world_turn.py`, and `chat_service.py` so both single and world chats share one
Archivist compression path, `CorrectionTable` feedback path, and event-triggered bond refresh path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol

from pydantic import ValidationError

from app.agents import archivist, bond_drafter, bond_selector
from app.agents.archivist import ArchivistMessage, ArchivistOutput, MemorableEvent, event_slug
from app.agents.base import AgentContext, Notice, run_non_critical
from app.agents.bond_drafter import BondPair, BondRecord
from app.llm.defaults import DEFAULT_MODELS
from app.llm.tokenizer import CorrectionTable, count_messages
from app.llm.usage import Usage
from app.repositories.messages_repo import MemorySnapshotRecord, MessageRecord
from app.schemas.chat import ChatSettings

NARRATOR_LABEL = "Người dẫn truyện"

SetState = Callable[[dict[str, Any]], Awaitable[None]]


class SaveSnapshot(Protocol):
    async def __call__(
        self, *, upto_seq: int, summary: str, events: Sequence[dict[str, Any]]
    ) -> MemorySnapshotRecord: ...


def summary_upto_of(state: Mapping[str, Any]) -> int:
    """Exclusive `seq` lower bound for unsummarized messages (`rec.seq >= summary_upto`)."""
    raw = state.get("summary_upto")
    if isinstance(raw, bool) or raw is None:
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def unsummarized_records(records: Sequence[MessageRecord], state: Mapping[str, Any]) -> list[MessageRecord]:
    """Return only messages not yet compressed into `state.summary`."""
    upto = summary_upto_of(state)
    return [rec for rec in records if rec.seq >= upto]


def observe_writer_usage(
    corrections: CorrectionTable,
    model: str,
    messages: Sequence[dict[str, Any]],
    prompt_tokens: int,
) -> None:
    """Feed real Writer `usage.prompt_tokens` back into the per-model correction table."""
    if prompt_tokens > 0 and model:
        corrections.observe(model, count_messages(messages), prompt_tokens)


def select_messages_to_compress(
    records: Sequence[MessageRecord],
    state: Mapping[str, Any],
    *,
    keep_recent: int,
    min_compress: int = 1,
) -> list[MessageRecord]:
    """Pick older unsummarized messages while keeping `keep_recent` newest unsummarized messages verbatim."""
    unsummarized = sorted(unsummarized_records(records, state), key=lambda r: r.seq)
    cutoff = len(unsummarized) - max(0, keep_recent)
    if cutoff < max(1, min_compress):
        return []
    return unsummarized[:cutoff]


def format_state_events(raw_events: Any) -> list[str]:
    """Format `chat.state.events` as `'<title>: <content>'` strings for the prompt memory layer."""
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, str | bytes):
        return []
    out: list[str] = []
    for item in raw_events:
        if isinstance(item, MemorableEvent):
            title, content = item.title.strip(), item.content.strip()
        elif isinstance(item, Mapping):
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or item.get("text") or "").strip()
        else:
            continue
        if title and content:
            out.append(f"{title}: {content}")
        elif title or content:
            out.append(title or content)
    return out


def parse_state_events(raw_events: Any) -> list[MemorableEvent]:
    """Leniently normalize `chat.state.events` into `MemorableEvent` objects."""
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, str | bytes):
        return []
    events: list[MemorableEvent] = []
    for item in raw_events:
        if isinstance(item, MemorableEvent):
            events.append(item)
            continue
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or item.get("text") or "").strip()
        if not title and not content:
            continue
        resolved_title = title or content[:40]
        resolved_content = content or resolved_title
        raw_id = str(item.get("id") or "").strip()
        events.append(
            MemorableEvent(
                id=raw_id or event_slug(resolved_title),
                title=resolved_title,
                content=resolved_content,
            )
        )
    return events


def _bond_records(state: Mapping[str, Any]) -> dict[str, BondRecord]:
    out: dict[str, BondRecord] = {}
    raw = state.get("bonds")
    if not isinstance(raw, Mapping):
        return out
    for key, value in raw.items():
        try:
            out[str(key)] = BondRecord.model_validate(value)
        except ValidationError:
            continue
    return out


def _bond_refresh_context(state: Mapping[str, Any]) -> str:
    parts: list[str] = []
    raw_summary = state.get("summary")
    if isinstance(raw_summary, str) and raw_summary.strip():
        parts.append(f"[Tóm tắt]\n{raw_summary.strip()}")
    formatted_events = format_state_events(state.get("events"))
    if formatted_events:
        parts.append("[Sự kiện đáng nhớ]\n" + "\n".join(f"- {line}" for line in formatted_events))
    return "\n\n".join(parts)


def _drain_or_fallback(agent_ctx: AgentContext, fallback: Sequence[Usage]) -> list[Usage]:
    drained = agent_ctx.llm.drain_usage()
    return drained if drained else list(fallback)


async def compress_memory(
    agent_ctx: AgentContext,
    model: str,
    state: dict[str, Any],
    records: Sequence[MessageRecord],
    *,
    user_name: str,
    speaker_names: Mapping[str, str],
    save_snapshot: SaveSnapshot,
    set_state: SetState,
    cfg: archivist.AgentConfig | None = None,
) -> tuple[ArchivistOutput | None, list[Notice], list[Usage]]:
    """Run Archivist non-critically on `records`, update `state`, and write a `MemorySnapshot`."""
    ordered = sorted(records, key=lambda r: r.seq)
    if not ordered:
        return None, [], []

    arch_messages: list[ArchivistMessage] = []
    for rec in ordered:
        if rec.speaker == "user":
            speaker_name = user_name
        elif rec.speaker == "narrator":
            speaker_name = NARRATOR_LABEL
        else:
            speaker_name = speaker_names.get(rec.speaker, rec.speaker)
        raw_prio = rec.meta.get("priority", 0) if isinstance(rec.meta, Mapping) else 0
        priority = raw_prio if isinstance(raw_prio, int) and not isinstance(raw_prio, bool) else 0
        arch_messages.append(
            ArchivistMessage(
                seq=rec.seq,
                speaker_name=speaker_name,
                content=rec.content,
                priority=priority,
            )
        )

    raw_summary = state.get("summary")
    previous_summary = raw_summary if isinstance(raw_summary, str) else ""
    previous_events = parse_state_events(state.get("events"))
    agent_cfg = cfg or archivist.AgentConfig(model=model)

    result = await run_non_critical(
        archivist.AGENT_ID,
        archivist.run(
            agent_ctx,
            agent_cfg,
            archivist.ArchivistInput(
                messages=arch_messages,
                previous_summary=previous_summary,
                previous_events=previous_events,
            ),
        ),
    )
    usages = _drain_or_fallback(agent_ctx, result.usage)
    if result.value is None:
        return None, result.notices, usages

    upto_seq = arch_messages[-1].seq + 1
    output = result.value.model_copy(update={"upto_seq": upto_seq})
    events_dicts = [ev.model_dump(mode="json") for ev in output.events]
    state["summary"] = output.summary
    state["summary_upto"] = upto_seq
    state["events"] = events_dicts

    await save_snapshot(upto_seq=upto_seq, summary=output.summary, events=events_dicts)
    await set_state(state)
    return output, result.notices, usages


async def refresh_bonds_on_events(
    agent_ctx: AgentContext,
    settings: ChatSettings,
    pairs: Sequence[BondPair],
    state: dict[str, Any],
    *,
    seq: int,
    set_state: SetState,
) -> tuple[dict[str, Any] | None, list[Notice], list[tuple[str, str, Usage]]]:
    """Re-run Bond Drafter + Selector when Archivist introduces or updates events.

    Uses `overwrite_unpinned=True` so agent-written bond fields evolve with the story while card-pinned
    and user-edited (`manual`) fields stay untouched.
    """
    pair_list = list(pairs)
    if not pair_list:
        return None, [], []

    context = _bond_refresh_context(state)
    notices: list[Notice] = []
    usage_items: list[tuple[str, str, Usage]] = []

    drafter_model = settings.models.bond_drafter or DEFAULT_MODELS["bond_drafter"]
    drafted_result = await run_non_critical(
        bond_drafter.AGENT_ID,
        bond_drafter.run(
            agent_ctx,
            bond_drafter.AgentConfig(model=drafter_model),
            bond_drafter.DrafterInput(pair_list, opening=context),
        ),
    )
    notices.extend(drafted_result.notices)
    for item in _drain_or_fallback(agent_ctx, drafted_result.usage):
        usage_items.append((bond_drafter.AGENT_ID, drafter_model, item))

    drafted = drafted_result.value
    if drafted is None or not any(drafted.options.values()):
        return None, notices, usage_items

    selector_model = settings.models.bond_selector or DEFAULT_MODELS["bond_selector"]
    picked = await run_non_critical(
        bond_selector.AGENT_ID,
        bond_selector.run(
            agent_ctx,
            bond_selector.AgentConfig(model=selector_model),
            bond_selector.SelectorInput(pair_list, drafted, opening=context),
        ),
    )
    notices.extend(picked.notices)
    for item in _drain_or_fallback(agent_ctx, picked.usage):
        usage_items.append((bond_selector.AGENT_ID, selector_model, item))

    selected = picked.value or {}
    if not selected:
        return None, notices, usage_items

    records = bond_selector.apply_selection(
        _bond_records(state),
        pair_list,
        selected,
        seq,
        overwrite_unpinned=True,
    )
    state["bonds"] = {key: record.model_dump(mode="json") for key, record in records.items()}
    await set_state(state)
    return state["bonds"], notices, usage_items
