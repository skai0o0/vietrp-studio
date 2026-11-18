"""Pure state command execution (`/time`, `/move`, `/addnpc`, `/removenpc`, `/listnpc`, `/clearnpc`).

Commands here mutate `chat.state` directly via `set_state` and emit SSE events (`StateEvent`, `NoticeEvent`,
`DoneEvent`) without persisting a chat message or calling any LLM.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from app.formats.world import Location, VietrpWorld
from app.pipeline.commands import ParsedInput
from app.pipeline.safety import CastMember
from app.schemas.events import DoneEvent, NoticeEvent, StateEvent, TurnEvent
from app.schemas.world_state import WorldState

STATE_COMMAND_KINDS = frozenset({"time", "move", "addnpc", "removenpc", "listnpc", "clearnpc", "unsupported"})

SetState = Callable[[dict[str, Any]], Awaitable[None]]


def _nfc_fold(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip()).casefold()


def npcs_from_state(raw_npcs: Any) -> list[CastMember]:
    """Convert `state['npcs']` dicts into `CastMember(..., is_npc=True)` entries for `safety.py`."""
    if not isinstance(raw_npcs, Sequence) or isinstance(raw_npcs, str | bytes):
        return []
    members: list[CastMember] = []
    for item in raw_npcs:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        raw_age = item.get("age")
        age = raw_age if isinstance(raw_age, int) and not isinstance(raw_age, bool) and raw_age >= 0 else None
        members.append(CastMember(name=name.strip(), age=age, is_npc=True))
    return members


def _mark_manual(state: dict[str, Any], key: str) -> None:
    raw = state.get("manual")
    manual = [str(item) for item in raw] if isinstance(raw, list) else []
    if key not in manual:
        manual.append(key)
    state["manual"] = manual


def _match_location(locations: Sequence[Location], target: str) -> Location | None:
    stripped = target.strip()
    if not stripped:
        return None
    for loc in locations:
        if loc.id == stripped:
            return loc
    folded_id = stripped.casefold()
    for loc in locations:
        if loc.id.casefold() == folded_id:
            return loc
    folded_name = _nfc_fold(stripped)
    for loc in locations:
        if _nfc_fold(loc.name) == folded_name:
            return loc
    return None


def _normalized_npcs(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = state.get("npcs")
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _format_npc_entry(item: Mapping[str, Any]) -> str:
    name = str(item.get("name") or "").strip()
    raw_age = item.get("age")
    age = raw_age if isinstance(raw_age, int) and not isinstance(raw_age, bool) and raw_age >= 0 else None
    desc = str(item.get("description") or "").strip()
    label = f"{name} ({age})" if age is not None else name
    return f"{label} - {desc}" if desc else label


async def _commit_world_or_single(
    state: dict[str, Any],
    *,
    world: VietrpWorld | None,
    manual_key: str,
    set_state: SetState,
) -> WorldState | None:
    if world is None:
        await set_state(state)
        return None
    _mark_manual(state, manual_key)
    ws = WorldState.model_validate(state)
    normalized = ws.model_dump(mode="json")
    state.clear()
    state.update(normalized)
    await set_state(state)
    return ws


async def execute_state_command(
    parsed: ParsedInput,
    *,
    state: dict[str, Any],
    set_state: SetState,
    world: VietrpWorld | None = None,
) -> list[TurnEvent]:
    """Execute one pure state command on `state` and return the SSE events to emit."""
    kind = parsed.kind
    if kind == "unsupported":
        return [NoticeEvent(code="command_unsupported", detail=parsed.command_name), DoneEvent(message_ids=[])]

    if kind == "time":
        if world is None:
            return [NoticeEvent(code="command_unsupported", detail="time"), DoneEvent(message_ids=[])]
        time_text = parsed.time_text.strip()
        if not time_text:
            return [NoticeEvent(code="command_invalid", detail="time"), DoneEvent(message_ids=[])]
        state["time"] = time_text
        ws = await _commit_world_or_single(state, world=world, manual_key="time", set_state=set_state)
        assert ws is not None
        return [
            StateEvent(state=ws, changed=["time"], confidence={"time": 1.0}),
            NoticeEvent(code="time_updated", detail=ws.time),
            DoneEvent(message_ids=[]),
        ]

    if kind == "move":
        if world is None:
            return [NoticeEvent(code="command_unsupported", detail="move"), DoneEvent(message_ids=[])]
        target = parsed.move_target.strip()
        if not target:
            return [NoticeEvent(code="command_invalid", detail="move"), DoneEvent(message_ids=[])]
        matched = _match_location(world.locations, target)
        if matched is None:
            return [NoticeEvent(code="move_target_unknown", detail=target), DoneEvent(message_ids=[])]
        state["location_id"] = matched.id
        ws = await _commit_world_or_single(state, world=world, manual_key="location_id", set_state=set_state)
        assert ws is not None
        return [
            StateEvent(state=ws, changed=["location_id"], confidence={"location_id": 1.0}),
            NoticeEvent(code="location_moved", detail=matched.name or matched.id),
            DoneEvent(message_ids=[]),
        ]

    if kind == "addnpc":
        name = parsed.npc_name.strip()
        if not name:
            return [NoticeEvent(code="command_invalid", detail="addnpc"), DoneEvent(message_ids=[])]
        npcs = _normalized_npcs(state)
        entry: dict[str, Any] = {
            "name": name,
            "age": parsed.npc_age,
            "description": parsed.npc_description.strip(),
        }
        folded = _nfc_fold(name)
        idx = next((i for i, item in enumerate(npcs) if _nfc_fold(str(item.get("name") or "")) == folded), None)
        if idx is None:
            npcs.append(entry)
        else:
            npcs[idx] = entry
        state["npcs"] = npcs
        ws = await _commit_world_or_single(state, world=world, manual_key="npcs", set_state=set_state)
        detail = f"{name} ({parsed.npc_age})" if parsed.npc_age is not None else name
        events: list[TurnEvent] = [NoticeEvent(code="npc_added", detail=detail)]
        if ws is not None:
            events.append(StateEvent(state=ws, changed=["npcs"], confidence={"npcs": 1.0}))
        events.append(DoneEvent(message_ids=[]))
        return events

    if kind == "removenpc":
        target = parsed.npc_name.strip()
        if not target:
            return [NoticeEvent(code="command_invalid", detail="removenpc"), DoneEvent(message_ids=[])]
        npcs = _normalized_npcs(state)
        folded = _nfc_fold(target)
        kept: list[dict[str, Any]] = []
        removed_name: str | None = None
        for item in npcs:
            item_name = str(item.get("name") or "")
            if _nfc_fold(item_name) == folded:
                if removed_name is None:
                    removed_name = item_name.strip() or target
            else:
                kept.append(item)
        if removed_name is None:
            return [NoticeEvent(code="npc_not_found", detail=target), DoneEvent(message_ids=[])]
        state["npcs"] = kept
        ws = await _commit_world_or_single(state, world=world, manual_key="npcs", set_state=set_state)
        events = [NoticeEvent(code="npc_removed", detail=removed_name)]
        if ws is not None:
            events.append(StateEvent(state=ws, changed=["npcs"], confidence={"npcs": 1.0}))
        events.append(DoneEvent(message_ids=[]))
        return events

    if kind == "listnpc":
        npcs = [item for item in _normalized_npcs(state) if str(item.get("name") or "").strip()]
        detail = "; ".join(_format_npc_entry(item) for item in npcs)
        return [NoticeEvent(code="npc_listed", detail=detail), DoneEvent(message_ids=[])]

    if kind == "clearnpc":
        npcs = _normalized_npcs(state)
        count = len(npcs)
        if count == 0:
            return [NoticeEvent(code="npc_cleared", detail="0"), DoneEvent(message_ids=[])]
        state["npcs"] = []
        ws = await _commit_world_or_single(state, world=world, manual_key="npcs", set_state=set_state)
        events = [NoticeEvent(code="npc_cleared", detail=str(count))]
        if ws is not None:
            events.append(StateEvent(state=ws, changed=["npcs"], confidence={"npcs": 1.0}))
        events.append(DoneEvent(message_ids=[]))
        return events

    return [NoticeEvent(code="command_unsupported", detail=parsed.command_name), DoneEvent(message_ids=[])]
