"""SillyTavern / VietRP file import with content-based format detection (WP-H)."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from app.core.errors import AppError
from app.formats.common import FormatWarning
from app.formats.png import MAX_PNG_BYTES, PngError, is_png, read_text_chunks
from app.formats.validate import FIELD_LONG_LIMIT, validate_card, validate_lorebook, validate_world

# Key under `data.extensions` where the full VietRP card is stored for lossless round-trips.
EXTENSION_KEY = "vietrp"

_NAME_MAX = 80
_TAG_MAX = 32
_TAGS_MAX = 20
_ENTRY_ID_PREFIX = "entry_"
# ST World Info position ids: 1 = after character definitions; other values map to before_char.
_ST_POSITION_AFTER = 1

_START_SPLIT = re.compile(r"<START>", re.IGNORECASE)
_CHAR_MACRO = re.compile(r"\{\{char\}\}", re.IGNORECASE)
_CHAR_LINE_PREFIX = re.compile(r"^[ \t]*\{\{char\}\}[ \t]*:[ \t]*", re.IGNORECASE | re.MULTILINE)

# Explicit age statements only (AGENTS.md section 4.6: never guess).
_AGE_PATTERNS = (
    re.compile(r"(?<!\d)(\d{1,4})(?!\s*\+)\s*tuổi", re.IGNORECASE),
    re.compile(r"\btuổi\s*[:=]\s*(\d{1,4})(?!\d)(?!\s*\+)", re.IGNORECASE),
    # The bare `age N` form needs `:` or `=`; a number followed by `+` is a rating, not an age.
    re.compile(r"\bage\s*[:=]\s*(\d{1,4})(?!\d)(?!\s*\+)", re.IGNORECASE),
    re.compile(r"(?<!\d)(\d{1,4})(?!\s*\+)[\s-]*(?:years?|yrs?)[\s-]*old", re.IGNORECASE),
    re.compile(r"(?<!\d)(\d{1,4})(?!\s*\+)\s*y/?o\b", re.IGNORECASE),
)


class FormatError(AppError):
    """A file could not be imported or exported; `code` is stable and machine-readable."""

    def __init__(self, code: str, message: str) -> None:
        # Contract (P1 WP-I): oversized input is 413, any other format problem is 422.
        super().__init__(code, message, status=413 if code == "file_too_large" else 422)


@dataclass
class ImportResult:
    kind: Literal["character", "world", "lorebook"]
    data: dict[str, Any]
    avatar: tuple[bytes, str] | None = None
    lorebook: dict[str, Any] | None = None
    warnings: list[FormatWarning] = field(default_factory=list)
    needs_age: bool = False
    # True when `lorebook` is the merged copy of the card's linked books taken from `extensions.vietrp`.
    merged_lorebook: bool = False


# ---------------------------------------------------------------- helpers


def parse_age(*texts: str) -> int | None:
    """Return the age only when every explicit age statement in `texts` agrees, else None.

    Conflicting statements (e.g. a parent's age and a child's age) are ambiguous, and a wrong
    adult age on a minor is a safety failure, so ambiguity means "unknown" (AGENTS.md 2.1, 4.6).
    """
    found: set[int] = set()
    for text in texts:
        for pattern in _AGE_PATTERNS:
            found.update(int(m.group(1)) for m in pattern.finditer(text))
    return next(iter(found)) if len(found) == 1 else None


def _validation_message(exc: ValidationError) -> str:
    # Locations and messages only; never echo input values.
    return "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _slug_name(raw: str, fallback: str) -> str:
    name = raw.strip()[:_NAME_MAX]
    return name or fallback


def _load_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise FormatError("invalid_json", "File is not valid UTF-8 JSON") from exc


# ---------------------------------------------------------------- lorebook mapping


def _entry_position(value: Any) -> str:
    if isinstance(value, str):
        return "after_char" if value == "after_char" else "before_char"
    if isinstance(value, int) and not isinstance(value, bool):
        return "after_char" if value == _ST_POSITION_AFTER else "before_char"
    return "before_char"


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    return default


def _map_entry(raw: dict[str, Any], index: int) -> dict[str, Any]:
    """Map one ST entry (character_book list item or World Info dict item) to a vietrp entry."""
    keys = raw.get("keys", raw.get("key"))
    secondary = raw.get("secondary_keys", raw.get("keysecondary"))
    enabled = not bool(raw["disable"]) if "disable" in raw else bool(raw.get("enabled", True))
    order = raw.get("insertion_order", raw.get("order", 0))
    return {
        "id": f"{_ENTRY_ID_PREFIX}{index + 1}",
        "title": _str(raw.get("comment")) or _str(raw.get("name")),
        "keys": _str_list(keys),
        "secondary_keys": _str_list(secondary),
        "selective": bool(raw.get("selective", False)),
        "constant": bool(raw.get("constant", False)),
        "priority": _int(order),
        "position": _entry_position(raw.get("position")),
        "select_mode": "keyword",
        "content": _str(raw.get("content")),
        "enabled": enabled,
    }


def _book_to_lorebook(book: dict[str, Any], fallback_name: str) -> dict[str, Any]:
    raw_entries = book.get("entries")
    items: list[dict[str, Any]] = []
    if isinstance(raw_entries, dict):
        items = [v for v in raw_entries.values() if isinstance(v, dict)]
    elif isinstance(raw_entries, list):
        items = [v for v in raw_entries if isinstance(v, dict)]
    lorebook: dict[str, Any] = {
        "format": "vietrp-lorebook",
        "spec_version": "1.0",
        "name": _slug_name(_str(book.get("name")), fallback_name),
        "description": _str(book.get("description")),
        "entries": [_map_entry(item, i) for i, item in enumerate(items)],
    }
    scan_depth = book.get("scan_depth")
    if isinstance(scan_depth, int) and not isinstance(scan_depth, bool) and scan_depth >= 1:
        lorebook["scan_depth"] = scan_depth
    token_budget = book.get("token_budget")
    if isinstance(token_budget, int) and not isinstance(token_budget, bool) and token_budget >= 0:
        lorebook["token_budget"] = token_budget
    return lorebook


def _validated_lorebook(data: dict[str, Any]) -> tuple[dict[str, Any], list[FormatWarning]]:
    try:
        book, warnings = validate_lorebook(data)
    except ValueError as exc:
        raise FormatError("lorebook_invalid", _exc_text(exc)) from exc
    return book.model_dump(mode="json"), warnings


def _exc_text(exc: Exception) -> str:
    return _validation_message(exc) if isinstance(exc, ValidationError) else str(exc)


# ---------------------------------------------------------------- card mapping


def _substitute_char(text: str, name: str) -> str:
    return _CHAR_MACRO.sub(lambda _m: name, text)


def _split_examples(mes_example: str, name: str) -> list[str]:
    out: list[str] = []
    for block in _START_SPLIT.split(mes_example):
        cleaned = _substitute_char(_CHAR_LINE_PREFIX.sub("", block).strip(), name)
        if cleaned:
            out.append(cleaned)
    return out


def _clean_tags(raw: Any) -> list[str]:
    out: list[str] = []
    for tag in _str_list(raw):
        value = tag.lower()[:_TAG_MAX]
        if value and value not in out:
            out.append(value)
    return out[:_TAGS_MAX]


def _st_to_card(data: dict[str, Any]) -> dict[str, Any]:
    name = _slug_name(_str(data.get("name")), "")
    if not name:
        raise FormatError("card_invalid", "Character card has no name")

    def clean(value: Any) -> str:
        return _substitute_char(_str(value).strip(), name)

    description = clean(data.get("description"))
    personality = clean(data.get("personality"))
    scenario = clean(data.get("scenario"))
    creator_notes = _str(data.get("creator_notes")).strip()

    extras: dict[str, str] = {}
    if description:
        if not personality and len(description) <= FIELD_LONG_LIMIT:
            personality = description
        else:
            extras["description"] = description
    if scenario:
        extras["scenario"] = scenario
    if creator_notes:
        extras["creator_notes"] = creator_notes

    greetings = [clean(data.get("first_mes"))]
    alternates = data.get("alternate_greetings")
    if isinstance(alternates, list):
        greetings.extend(clean(item) for item in alternates)

    # Age is read from the raw ST text so a macro substitution can never invent one.
    age = parse_age(_str(data.get("description")), _str(data.get("personality")), _str(data.get("scenario")))

    return {
        "format": "vietrp-card",
        "spec_version": "1.0",
        "name": name,
        "age": age,
        "is_fictional": True,
        "personality": personality,
        "speech": {"examples": _split_examples(_str(data.get("mes_example")), name)},
        "greetings": [g for g in greetings if g],
        "extras": extras,
        "tags": _clean_tags(data.get("tags")),
    }


def _import_card(data: dict[str, Any], fallback_book_name: str) -> ImportResult:
    extension = data.get("extensions", {}).get(EXTENSION_KEY) if isinstance(data.get("extensions"), dict) else None
    card_dict: dict[str, Any] | None = None
    lorebook_dict: dict[str, Any] | None = None
    warnings: list[FormatWarning] = []
    merged = False

    if isinstance(extension, dict) and isinstance(extension.get("card"), dict):
        try:
            card, warnings = validate_card(extension["card"], allow_missing_age=True)
            card_dict = card.model_dump(mode="json")
            stored_book = extension.get("lorebook")
            if isinstance(stored_book, dict):
                lorebook_dict, book_warnings = _validated_lorebook(stored_book)
                warnings.extend(book_warnings)
                merged = True
        except (ValueError, FormatError):
            # A damaged extension must not block the import: fall back to the ST fields.
            card_dict, lorebook_dict, warnings, merged = None, None, [], False

    if card_dict is None:
        try:
            card, warnings = validate_card(_st_to_card(data), allow_missing_age=True)
        except ValueError as exc:
            raise FormatError("card_invalid", _exc_text(exc)) from exc
        card_dict = card.model_dump(mode="json")
        book = data.get("character_book")
        if isinstance(book, dict) and book.get("entries"):
            lorebook_dict, book_warnings = _validated_lorebook(
                _book_to_lorebook(book, _slug_name(f"{card.name} lorebook", "lorebook"))
            )
            warnings.extend(book_warnings)

    return ImportResult(
        kind="character",
        data=card_dict,
        lorebook=lorebook_dict,
        warnings=warnings,
        needs_age=card_dict["age"] is None,
        merged_lorebook=merged,
    )


# ---------------------------------------------------------------- detection


def _decode_png_payload(content: bytes) -> dict[str, Any]:
    try:
        texts = read_text_chunks(content)
    except PngError as exc:
        raise FormatError(exc.code, exc.message) from exc
    for keyword in ("ccv3", "chara"):  # ccv3 is preferred when both exist
        encoded = texts.get(keyword)
        if encoded is None:
            continue
        try:
            payload = _load_json(base64.b64decode(encoded, validate=False))
        except (binascii.Error, ValueError) as exc:
            raise FormatError("png_card_invalid", "PNG card payload is not valid base64 JSON") from exc
        if not isinstance(payload, dict):
            raise FormatError("png_card_invalid", "PNG card payload is not a JSON object")
        return payload
    raise FormatError("png_no_card", "PNG contains no character card data")


def _is_bare_card(obj: dict[str, Any]) -> bool:
    return isinstance(obj.get("name"), str) and any(
        key in obj for key in ("description", "personality", "first_mes", "scenario", "mes_example")
    )


def import_file(content: bytes, filename: str) -> ImportResult:
    """Detect the format of `content` and convert it to a validated VietRP structure."""
    if len(content) > MAX_PNG_BYTES:
        raise FormatError("file_too_large", "File exceeds the size limit")

    avatar: tuple[bytes, str] | None = None
    if is_png(content):
        obj = _decode_png_payload(content)
        avatar = (content, "image/png")
    else:
        parsed = _load_json(content)
        if not isinstance(parsed, dict):
            raise FormatError("format_unknown", "Unrecognized file format")
        obj = parsed

    fmt = obj.get("format")
    stem = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].rsplit(".", 1)[0]
    result: ImportResult

    if fmt == "vietrp-card":
        try:
            card, warnings = validate_card(obj, allow_missing_age=True)
        except ValueError as exc:
            raise FormatError("card_invalid", _exc_text(exc)) from exc
        dumped = card.model_dump(mode="json")
        result = ImportResult("character", dumped, warnings=warnings, needs_age=dumped["age"] is None)
    elif fmt == "vietrp-world":
        try:
            world, warnings = validate_world(obj)
        except ValueError as exc:
            raise FormatError("world_invalid", _exc_text(exc)) from exc
        result = ImportResult("world", world.model_dump(mode="json"), warnings=warnings)
    elif fmt == "vietrp-lorebook":
        data, warnings = _validated_lorebook(obj)
        result = ImportResult("lorebook", data, warnings=warnings)
    elif obj.get("spec") in ("chara_card_v2", "chara_card_v3") and isinstance(obj.get("data"), dict):
        result = _import_card(obj["data"], stem)
    elif isinstance(obj.get("entries"), (dict, list)):
        extension = obj.get("extensions", {}).get(EXTENSION_KEY) if isinstance(obj.get("extensions"), dict) else None
        if isinstance(extension, dict):
            data, warnings = _validated_lorebook(extension)
        else:
            data, warnings = _validated_lorebook(_book_to_lorebook(obj, _slug_name(stem, "lorebook")))
        result = ImportResult("lorebook", data, warnings=warnings)
    elif _is_bare_card(obj):
        result = _import_card(obj, stem)
    else:
        raise FormatError("format_unknown", "Unrecognized file format")

    result.avatar = avatar
    return result
