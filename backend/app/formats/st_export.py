"""Export VietRP data as VietRP JSON or SillyTavern CCv2/CCv3 (JSON or PNG) (WP-H)."""

from __future__ import annotations

import base64
import json
import re
import unicodedata
from typing import Any, Literal

from app.formats.png import is_png, placeholder_png, write_text_chunks
from app.formats.st_import import EXTENSION_KEY, FormatError
from app.formats.validate import validate_card, validate_lorebook, validate_world

JSON_MIME = "application/json"
PNG_MIME = "image/png"
_FILENAME_FALLBACK = "export"
_FILENAME_MAX = 60
_ST_POSITION = {"before_char": 0, "after_char": 1}


def _dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def _file_stem(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name.replace("đ", "d").replace("Đ", "D"))
    ascii_name = folded.encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()[:_FILENAME_MAX]
    return stem or _FILENAME_FALLBACK


def _description(card: dict[str, Any]) -> str:
    """Compose the ST `description` from the structured fields (labels are Vietnamese card content)."""
    parts: list[str] = []
    if card.get("age") is not None:
        parts.append(f"Tuổi: {card['age']}")  # keeps an explicit age discoverable on a plain ST re-import
    for label, key in (("Ngoại hình", "appearance"), ("Tiểu sử", "backstory"), ("Mục tiêu", "goals")):
        value = str(card.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    extra = str(card.get("extras", {}).get("description") or "").strip()
    if extra:
        parts.append(extra)
    return "\n".join(parts)


def _mes_example(card: dict[str, Any]) -> str:
    examples = card.get("speech", {}).get("examples", [])
    return "\n".join(f"<START>\n{example}" for example in examples)


def _character_book(book: dict[str, Any]) -> dict[str, Any]:
    entries = [
        {
            "id": index,
            "keys": entry["keys"],
            "secondary_keys": entry["secondary_keys"],
            "comment": entry["title"],
            "name": entry["title"],
            "content": entry["content"],
            "enabled": entry["enabled"],
            "insertion_order": entry["priority"],
            "priority": entry["priority"],
            "selective": entry["selective"],
            "constant": entry["constant"],
            "position": entry["position"],
            "case_sensitive": False,
            "extensions": {},
        }
        for index, entry in enumerate(book["entries"])
    ]
    return {
        "name": book["name"],
        "description": book["description"],
        "scan_depth": book["scan_depth"],
        "token_budget": book["token_budget"],
        "recursive_scanning": False,
        "extensions": {},
        "entries": entries,
    }


def _card_data(card: dict[str, Any], lorebook: dict[str, Any] | None, meta: dict[str, Any]) -> dict[str, Any]:
    greetings: list[str] = card.get("greetings", [])
    extras: dict[str, str] = card.get("extras", {})
    data: dict[str, Any] = {
        "name": card["name"],
        "description": _description(card),
        "personality": card.get("personality", ""),
        "scenario": extras.get("scenario", ""),
        "first_mes": greetings[0] if greetings else "",
        "mes_example": _mes_example(card),
        "creator_notes": extras.get("creator_notes") or str(meta.get("creator_notes", "")),
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": greetings[1:],
        "tags": card.get("tags", []),
        "creator": str(meta.get("creator", "")),
        "character_version": str(meta.get("character_version", "")),
        "extensions": {EXTENSION_KEY: {"card": card, "lorebook": lorebook}},
    }
    if lorebook is not None:
        data["character_book"] = _character_book(lorebook)
    return data


def _ccv2(data: dict[str, Any]) -> dict[str, Any]:
    mirrored = {k: data[k] for k in ("name", "description", "personality", "scenario", "first_mes", "mes_example")}
    return {**mirrored, "spec": "chara_card_v2", "spec_version": "2.0", "data": data}


def _ccv3(data: dict[str, Any]) -> dict[str, Any]:
    v3_data = {**data, "group_only_greetings": [], "nickname": ""}
    return {"spec": "chara_card_v3", "spec_version": "3.0", "data": v3_data}


def _b64(obj: Any) -> str:
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode("ascii")


def export_character(
    card: dict[str, Any],
    *,
    fmt: Literal["vietrp", "ccv2", "ccv3"],
    as_: Literal["json", "png"],
    avatar: bytes | None,
    lorebook: dict[str, Any] | None,
    meta: dict[str, Any],
) -> tuple[bytes, str, str]:
    """Return (body, mime, filename). ST formats embed the full VietRP card for lossless re-import."""
    try:
        card_model, _ = validate_card(card, allow_missing_age=True)
        card_dict = card_model.model_dump(mode="json")
        book_dict = validate_lorebook(lorebook)[0].model_dump(mode="json") if lorebook is not None else None
    except ValueError as exc:
        raise FormatError("export_invalid", "Data to export failed validation") from exc

    stem = _file_stem(card_dict["name"])
    if fmt == "vietrp":
        if as_ != "json":
            raise FormatError("export_unsupported", "VietRP cards export as JSON only")
        return _dumps(card_dict), JSON_MIME, f"{stem}.card.json"

    data = _card_data(card_dict, book_dict, meta)
    if as_ == "json":
        payload = _ccv2(data) if fmt == "ccv2" else _ccv3(data)
        return _dumps(payload), JSON_MIME, f"{stem}.{fmt}.json"

    if avatar is not None and not is_png(avatar):
        raise FormatError("avatar_not_png", "Only PNG avatars can carry a card")
    base = avatar if avatar is not None else placeholder_png()
    body = write_text_chunks(base, {"chara": _b64(_ccv2(data)), "ccv3": _b64(_ccv3(data))})
    return body, PNG_MIME, f"{stem}.png"


def export_world(world: dict[str, Any], *, meta: dict[str, Any]) -> tuple[bytes, str, str]:
    try:
        model, _ = validate_world(world)
    except ValueError as exc:
        raise FormatError("export_invalid", "Data to export failed validation") from exc
    dumped = model.model_dump(mode="json")
    return _dumps(dumped), JSON_MIME, f"{_file_stem(dumped['name'])}.world.json"


def _wi_entries(book: dict[str, Any]) -> dict[str, Any]:
    return {
        str(index): {
            "uid": index,
            "key": entry["keys"],
            "keysecondary": entry["secondary_keys"],
            "comment": entry["title"],
            "content": entry["content"],
            "constant": entry["constant"],
            "selective": entry["selective"],
            "order": entry["priority"],
            "position": _ST_POSITION[entry["position"]],
            "disable": not entry["enabled"],
            "displayIndex": index,
        }
        for index, entry in enumerate(book["entries"])
    }


def export_lorebook(
    book: dict[str, Any], *, fmt: Literal["vietrp", "st"], meta: dict[str, Any]
) -> tuple[bytes, str, str]:
    try:
        model, _ = validate_lorebook(book)
    except ValueError as exc:
        raise FormatError("export_invalid", "Data to export failed validation") from exc
    dumped = model.model_dump(mode="json")
    stem = _file_stem(dumped["name"])
    if fmt == "vietrp":
        return _dumps(dumped), JSON_MIME, f"{stem}.lorebook.json"
    payload = {
        "name": dumped["name"],
        "description": dumped["description"],
        "entries": _wi_entries(dumped),
        "extensions": {EXTENSION_KEY: dumped},
    }
    return _dumps(payload), JSON_MIME, f"{stem}.worldinfo.json"
