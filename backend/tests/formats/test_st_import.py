from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from app.formats.png import placeholder_png, write_text_chunks
from app.formats.st_import import FormatError, import_file, parse_age

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "st"


def _load(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _enc(obj: object) -> str:
    return base64.b64encode(json.dumps(obj, ensure_ascii=False).encode()).decode()


def test_import_ccv2_heuristics() -> None:
    result = import_file(_load("ccv2_minh_anh.json"), "minh_anh.json")
    card = result.data
    assert result.kind == "character"
    assert card["name"] == "Minh Anh"
    assert card["age"] == 20
    assert result.needs_age is False
    assert card["is_fictional"] is True
    # ST personality exists, so it wins; the short description is kept in extras.
    assert card["personality"] == "Dịu dàng, hay ngại ngùng"
    assert card["extras"]["description"].startswith("Minh Anh là một cô gái 20 tuổi")
    assert card["extras"]["scenario"] == "{{user}} ghé quán vào một chiều mưa."
    assert card["extras"]["creator_notes"] == "Card thử nghiệm."
    assert card["greetings"] == ["Chào {{user}}, Minh Anh đây. Trời mưa to quá nhỉ?", "Ơ, {{user}} đến rồi à?"]
    assert card["speech"]["examples"] == [
        "{{user}}: Em khỏe không?\nDạ em khỏe, cảm ơn anh.",
        "Hôm nay quán đông lắm.",
    ]
    assert card["tags"] == ["đời thường", "slice-of-life"]
    assert result.avatar is None


def test_import_ccv2_character_book() -> None:
    result = import_file(_load("ccv2_minh_anh.json"), "x.json")
    book = result.lorebook
    assert book is not None
    assert book["name"] == "Quán cà phê"
    assert book["scan_depth"] == 4
    assert book["token_budget"] == 300
    entry = book["entries"][0]
    assert entry["keys"] == ["quán", "cà phê"]
    assert entry["secondary_keys"] == ["mưa"]
    assert entry["priority"] == 7
    assert entry["position"] == "after_char"
    assert entry["selective"] is True
    assert entry["title"] == "Quán"


def test_import_ccv3_without_age_needs_age() -> None:
    result = import_file(_load("ccv3_no_age.json"), "lao_bon.json")
    assert result.data["age"] is None
    assert result.needs_age is True
    assert result.data["personality"] == "Ông lão bán vé số ở góc chợ."
    assert result.lorebook is None
    assert any(w.code == "age_missing" for w in result.warnings)


def test_import_bare_v1_with_explicit_age() -> None:
    result = import_file(_load("bare_v1.json"), "ha.json")
    assert result.data["name"] == "Tiểu Hà"
    assert result.data["age"] == 9
    assert result.needs_age is False


def test_import_world_info() -> None:
    result = import_file(_load("worldinfo.json"), "cho_ga.json")
    assert result.kind == "lorebook"
    assert result.data["name"] == "cho_ga"
    first, second = result.data["entries"]
    assert first["keys"] == ["chợ", "vé số"]
    assert first["constant"] is True
    assert first["priority"] == 100
    assert first["position"] == "after_char"
    assert first["enabled"] is True
    assert second["selective"] is True
    assert second["secondary_keys"] == ["đêm"]
    assert second["enabled"] is False
    assert second["position"] == "before_char"
    assert first["id"] != second["id"]


def test_import_png_prefers_ccv3_and_returns_avatar() -> None:
    v2 = json.loads(_load("ccv2_minh_anh.json"))
    v3 = json.loads(_load("ccv3_no_age.json"))
    png = write_text_chunks(placeholder_png(), {"chara": _enc(v2), "ccv3": _enc(v3)})
    result = import_file(png, "card.png")
    assert result.data["name"] == "Lão Bốn"
    assert result.avatar == (png, "image/png")

    only_v2 = write_text_chunks(placeholder_png(), {"chara": _enc(v2)})
    assert import_file(only_v2, "card.png").data["name"] == "Minh Anh"


def test_png_without_card_rejected() -> None:
    with pytest.raises(FormatError) as exc:
        import_file(placeholder_png(), "empty.png")
    assert exc.value.code == "png_no_card"


def test_png_with_corrupt_crc_rejected() -> None:
    png = bytearray(write_text_chunks(placeholder_png(), {"chara": "e30="}))
    png[bytes(png).index(b"tEXt") + 5] ^= 0xFF
    with pytest.raises(FormatError) as exc:
        import_file(bytes(png), "bad.png")
    assert exc.value.code == "png_crc_mismatch"


@pytest.mark.parametrize("content", [b'{"foo": 1}', b"[1, 2]", b'{"entries": 5}'])
def test_unknown_format_rejected(content: bytes) -> None:
    with pytest.raises(FormatError) as exc:
        import_file(content, "x.json")
    assert exc.value.code == "format_unknown"


def test_invalid_json_rejected() -> None:
    with pytest.raises(FormatError) as exc:
        import_file(b"{not json", "x.json")
    assert exc.value.code == "invalid_json"


def test_card_without_name_rejected() -> None:
    body = json.dumps({"spec": "chara_card_v2", "data": {"name": "  ", "description": "x"}}).encode()
    with pytest.raises(FormatError) as exc:
        import_file(body, "x.json")
    assert exc.value.code == "card_invalid"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Cô ấy 20 tuổi", 20),
        ("Tuổi: 17", 17),
        ("age: 25", 25),
        ("Age: 31", 31),
        ("Age = 31", 31),
        # Bare `age N` without a separator is no longer accepted: ambiguous means unknown.
        ("Age 31", None),
        ("Rated age 18+ content", None),
        ("age: 18+", None),
        ("18+ years old content", None),
        ("age: 16, a 16 years old girl", 16),
        # Conflicting statements are ambiguous: never pick one (AGENTS.md 2.1).
        ("Her father, age: 45, raised her alone. She is 16 years old.", None),
        ("Her father, age 45, raised her alone. She is 16 years old.", 16),
        ("Mẹ cô 40 tuổi. Cô ấy 15 years old.", None),
        ("A 15 year old girl. Rated age 18+ content.", 15),
        ("a 19 years old girl", 19),
        ("a 19-year-old girl", 19),
        ("22 y/o", 22),
        ("Cô gái trẻ, không rõ tuổi", None),
        ("Sinh năm 2000", None),
        ("Lives at number 20", None),
        ("", None),
    ],
)
def test_parse_age(text: str, expected: int | None) -> None:
    assert parse_age(text) == expected


def test_never_guess_age_from_other_fields() -> None:
    body = json.dumps({"name": "A", "description": "Một người bí ẩn.", "first_mes": "Tôi 30 tuổi."}).encode()
    result = import_file(body, "a.json")
    assert result.data["age"] is None
    assert result.needs_age is True


def test_parse_age_conflict_across_texts() -> None:
    assert parse_age("Cô ấy 15 tuổi", "Mẹ cô ấy 40 tuổi") is None
    assert parse_age("Cô ấy 15 tuổi", "She is 15 years old") == 15


def test_import_conflicting_ages_needs_age() -> None:
    body = json.dumps({"name": "A", "description": "Mẹ cô 40 tuổi. Cô ấy 15 years old.", "first_mes": "Chào"}).encode()
    result = import_file(body, "a.json")
    assert result.data["age"] is None and result.needs_age is True


def test_deeply_nested_json_is_invalid_json() -> None:
    body = b"[" * 100_000 + b"]" * 100_000
    with pytest.raises(FormatError) as exc:
        import_file(body, "deep.json")
    assert exc.value.code == "invalid_json" and exc.value.status == 422
