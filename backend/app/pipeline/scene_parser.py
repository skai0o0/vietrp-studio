"""Streaming `<scene>` block filter, lenient JSON parser, and scene state merger (architecture §4.6, AGENTS §4.5)."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from app.agents.base import Notice
from app.schemas.chat import GroupWriteMode
from app.schemas.world_state import CharacterSceneState, SceneDelta, SceneState

SCENE_OPEN_TAG = "<scene>"
SCENE_CLOSE_TAG = "</scene>"
SCENE_PREFIX = "<scene"
CHAR_SCENE_FIELDS: tuple[str, ...] = ("mood", "outfit", "pose", "holding", "condition")
_SCENE_TOP_KEYS = frozenset({"env", "chars", "items"})

_OPEN_TAG_RE = re.compile(r"^<scene\b[^>]*>", re.IGNORECASE)
_OPEN_PREFIX_RE = re.compile(r"^<scene(?=\s|\{)", re.IGNORECASE)
_CLOSE_TAG_RE = re.compile(r"</scene\s*>", re.IGNORECASE)
_FENCE_OPEN_RE = re.compile(r"^```(?:[a-zA-Z0-9_-]+)?\s*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")


class SceneStreamFilter:
    """Filters `<scene>...</scene>` blocks out of a Writer token stream in real time.

    Text before `<scene` is forwarded immediately. Suffixes that partially match `<scene`
    (such as `"<"` or `"<sc"`) are held until the next chunk confirms or disproves the tag.
    Once `<scene` is seen, forwarding stops and all subsequent text goes into `scene_buffer`.
    """

    def __init__(self) -> None:
        self._capturing = False
        self._finished = False
        self._pending = ""
        self._visible_chunks: list[str] = []
        self._scene_chunks: list[str] = []

    @property
    def visible_text(self) -> str:
        """All user-visible text emitted so far."""
        return "".join(self._visible_chunks)

    @property
    def scene_buffer(self) -> str:
        """Buffered `<scene...` text captured once `<scene` was encountered."""
        return "".join(self._scene_chunks)

    def feed(self, chunk: str) -> str:
        """Feed one streamed delta chunk and return any text safe to show to the user."""
        if self._finished or not chunk:
            return ""
        if self._capturing:
            self._scene_chunks.append(chunk)
            return ""

        buf = self._pending + chunk
        self._pending = ""
        idx = buf.lower().find(SCENE_PREFIX)
        if idx != -1:
            visible = buf[:idx]
            if visible:
                self._visible_chunks.append(visible)
            self._scene_chunks.append(buf[idx:])
            self._capturing = True
            return visible

        lowered = buf.lower()
        max_hold = min(len(buf), len(SCENE_PREFIX) - 1)
        for length in range(max_hold, 0, -1):
            if lowered.endswith(SCENE_PREFIX[:length]):
                self._pending = buf[-length:]
                visible = buf[:-length]
                if visible:
                    self._visible_chunks.append(visible)
                return visible

        self._visible_chunks.append(buf)
        return buf

    def finish(self) -> tuple[str, str | None]:
        """Flush any trailing partial non-`<scene` text and return `(trailing_visible, scene_block_or_none)`."""
        if self._finished:
            return ("", self.scene_buffer if self._capturing else None)
        self._finished = True
        trailing = ""
        if not self._capturing and self._pending:
            trailing = self._pending
            self._visible_chunks.append(trailing)
            self._pending = ""
        return (trailing, self.scene_buffer if self._capturing else None)


def strip_scene_block(text: str) -> tuple[str, str | None]:
    """Split complete Writer output into `(visible_text, raw_scene_block_or_none)` for Director/persistence."""
    idx = text.lower().find(SCENE_PREFIX)
    if idx == -1:
        return (text, None)
    return (text[:idx].rstrip(), text[idx:])


def _strip_tags_and_fences(raw: str) -> str:
    body = raw.strip()
    if not body:
        return ""
    if _OPEN_TAG_RE.match(body):
        body = _OPEN_TAG_RE.sub("", body, count=1).strip()
    elif _OPEN_PREFIX_RE.match(body):
        body = _OPEN_PREFIX_RE.sub("", body, count=1).strip()
    close_match = _CLOSE_TAG_RE.search(body)
    if close_match is not None:
        body = body[: close_match.start()].strip()
    if body.startswith("```"):
        body = _FENCE_OPEN_RE.sub("", body, count=1).strip()
        body = _FENCE_CLOSE_RE.sub("", body, count=1).strip()
    return body


def _read_double_quoted(text: str, start: int) -> tuple[str, int]:
    i = start + 1
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            return text[start : i + 1], i + 1
        i += 1
    return text[start:], n


def _read_single_quoted_as_double(text: str, start: int) -> tuple[str, int]:
    i = start + 1
    n = len(text)
    inner: list[str] = []
    while i < n:
        ch = text[i]
        if ch == "\\" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "'":
                inner.append("'")
            elif nxt == '"':
                inner.append('\\"')
            else:
                inner.append("\\" + nxt)
            i += 2
            continue
        if ch == '"':
            inner.append('\\"')
            i += 1
            continue
        if ch == "\n":
            inner.append("\\n")
            i += 1
            continue
        if ch == "\r":
            inner.append("\\r")
            i += 1
            continue
        if ch == "\t":
            inner.append("\\t")
            i += 1
            continue
        if ch == "'":
            return '"' + "".join(inner) + '"', i + 1
        inner.append(ch)
        i += 1
    return text[start:], n


def _repair_json_syntax(text: str, *, convert_single_quotes: bool) -> str:
    """Strip trailing commas before `}`/`]`, close unclosed braces, and optionally convert `'...'` strings."""
    out: list[str] = []
    stack: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            segment, i = _read_double_quoted(text, i)
            out.append(segment)
            continue
        if convert_single_quotes and ch == "'":
            segment, i = _read_single_quoted_as_double(text, i)
            out.append(segment)
            continue
        if ch == ",":
            j = i + 1
            while j < n and text[j] in " \t\r\n":
                j += 1
            if j < n and text[j] in ("}", "]"):
                i += 1
                continue
            out.append(ch)
            i += 1
            continue
        if ch == "{":
            stack.append("}")
            out.append(ch)
            i += 1
            continue
        if ch == "[":
            stack.append("]")
            out.append(ch)
            i += 1
            continue
        if ch in ("}", "]"):
            if stack and stack[-1] == ch:
                stack.pop()
            out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    if stack:
        out.extend(reversed(stack))
    return "".join(out)


def _decode_scene_dict(body: str) -> dict[str, Any]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        repaired = _repair_json_syntax(body, convert_single_quotes=False)
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            repaired_sq = _repair_json_syntax(body, convert_single_quotes=True)
            try:
                parsed = json.loads(repaired_sq)
            except json.JSONDecodeError:
                parsed = ast.literal_eval(repaired)
    if not isinstance(parsed, dict):
        raise ValueError("scene block JSON root must be an object")
    return parsed


def _scalar_to_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if value is None:
        return ""
    raise ValueError(f"expected scalar value, got {type(value).__name__}")


def _normalize_scene_delta(raw_dict: dict[str, Any]) -> SceneDelta:
    env_out: dict[str, str] = {}
    if "env" in raw_dict and raw_dict["env"] is not None:
        raw_env = raw_dict["env"]
        if not isinstance(raw_env, dict):
            raise ValueError("scene.env must be an object")
        for key, value in raw_env.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("scene.env keys must be non-empty strings")
            env_out[key] = _scalar_to_str(value)

    chars_out: dict[str, CharacterSceneState] = {}
    if "chars" in raw_dict and raw_dict["chars"] is not None:
        raw_chars = raw_dict["chars"]
        if not isinstance(raw_chars, dict):
            raise ValueError("scene.chars must be an object")
        for cid, raw_state in raw_chars.items():
            if not isinstance(cid, str) or not cid.strip():
                raise ValueError("scene.chars keys must be non-empty strings")
            if not isinstance(raw_state, dict):
                raise ValueError(f"scene.chars[{cid!r}] must be an object")
            kwargs: dict[str, str] = {}
            for field_name in CHAR_SCENE_FIELDS:
                if field_name in raw_state:
                    kwargs[field_name] = _scalar_to_str(raw_state[field_name])
            # Constructing with only the supplied keys preserves `model_fields_set` for explicit "" clears.
            chars_out[cid] = CharacterSceneState(**kwargs)

    items_out: list[str] | None = None
    if "items" in raw_dict and raw_dict["items"] is not None:
        raw_items = raw_dict["items"]
        if not isinstance(raw_items, list):
            raise ValueError("scene.items must be a list or null")
        items_out = [_scalar_to_str(item) for item in raw_items]

    unknown_top = set(raw_dict) - _SCENE_TOP_KEYS
    if unknown_top and not env_out and not chars_out and items_out is None and "items" not in raw_dict:
        # An object containing only unrecognised keys is likely malformed rather than an intentional empty delta.
        if "env" not in raw_dict and "chars" not in raw_dict:
            raise ValueError("scene object contains no recognised keys")

    return SceneDelta(env=env_out, chars=chars_out, items=items_out)


def parse_scene_block(raw: str | None) -> tuple[SceneDelta | None, Notice | None]:
    """Parse an optional `<scene>` block into a `SceneDelta`, or emit a non-fatal notice on failure."""
    if raw is None:
        return (None, None)
    body = _strip_tags_and_fences(raw)
    if not body:
        return (None, None)
    try:
        parsed = _decode_scene_dict(body)
        delta = _normalize_scene_delta(parsed)
    except (ValueError, SyntaxError, ValidationError) as exc:
        return (
            None,
            Notice(
                code="scene_parse_failed",
                agent="writer",
                detail=f"invalid scene block: {type(exc).__name__}",
            ),
        )
    return (delta, None)


def visible_scene(scene: SceneState, present_ids: Sequence[str]) -> SceneState:
    """Return a copy of `scene` keeping only `chars` for characters currently in `present_ids`."""
    present_set = set(present_ids)
    return SceneState(
        env=dict(scene.env),
        chars={cid: st.model_copy() for cid, st in scene.chars.items() if cid in present_set},
        items=list(scene.items),
    )


def merge_scene(
    scene: SceneState,
    delta: SceneDelta | None,
    *,
    speaker_id: str,
    write_mode: GroupWriteMode,
    present_ids: Sequence[str] | None = None,
) -> SceneState:
    """Merge `delta` into `scene`, enforcing per-speaker write rules and optional presence hiding."""
    env = dict(scene.env)
    chars = {cid: st.model_copy() for cid, st in scene.chars.items()}
    items = list(scene.items)

    if delta is not None:
        env.update(delta.env)
        if delta.items is not None:
            items = list(delta.items)

        allow_all_chars = write_mode == "single_call" or speaker_id == "narrator"
        for cid, patch_state in delta.chars.items():
            if not allow_all_chars and cid != speaker_id:
                continue
            base = chars.get(cid) or CharacterSceneState()
            updates: dict[str, str] = {}
            for field_name in CHAR_SCENE_FIELDS:
                value = getattr(patch_state, field_name)
                if field_name in patch_state.model_fields_set or value != "":
                    updates[field_name] = value
            chars[cid] = base.model_copy(update=updates)

    merged = SceneState(env=env, chars=chars, items=items)
    if present_ids is not None:
        return visible_scene(merged, present_ids)
    return merged
