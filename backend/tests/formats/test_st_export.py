from __future__ import annotations

import json
from typing import Any, Literal
from uuid import uuid4

import pytest

from app.formats.card import VietrpCard
from app.formats.lorebook import Lorebook
from app.formats.png import placeholder_png, read_text_chunks
from app.formats.st_export import export_character, export_lorebook, export_world
from app.formats.st_import import FormatError, import_file


def _card() -> dict[str, Any]:
    return VietrpCard.model_validate(
        {
            "name": "Trần Hạ",
            "age": 24,
            "aliases": ["Hạ"],
            "tagline": "Thám tử tự do",
            "appearance": "Cao gầy, tóc ngắn.",
            "personality": "Lạnh lùng nhưng tốt bụng.",
            "backstory": "Từng là cảnh sát.",
            "goals": "Tìm ra sự thật.",
            "limits": ["Không dùng súng"],
            "secrets": [{"id": "ban_than", "content": "Có anh trai mất tích.", "reveal_when": "tin tưởng"}],
            "speech": {"style": "Ngắn gọn", "catchphrases": ["Hừm."], "examples": ["{{user}}: Chào\nTrần Hạ: Ừ."]},
            "addressing": {"default": "anh", "user": "cậu", "by_character": {"bao_an": "chú"}},
            "relationships": {"user": "đồng nghiệp", "by_character": {"bao_an": "chú ruột"}},
            "greetings": ["Chào.", "Lại là cậu à?", "Vào đi."],
            "lorebook_ids": [str(uuid4())],
            "extras": {"scenario": "Văn phòng thám tử", "creator_notes": "ghi chú", "description": "mô tả dài"},
            "tags": ["trinh-thám", "hiện-đại"],
        }
    ).model_dump(mode="json")


def _book() -> dict[str, Any]:
    return Lorebook.model_validate(
        {
            "name": "Thành phố",
            "description": "Bối cảnh",
            "scan_depth": 10,
            "token_budget": 400,
            "entries": [
                {
                    "id": "cho_dem",
                    "title": "Chợ đêm",
                    "keys": ["chợ"],
                    "secondary_keys": ["đêm"],
                    "selective": True,
                    "priority": 3,
                    "position": "after_char",
                    "select_mode": "both",
                    "content": "Họp lúc nửa đêm.",
                    "enabled": False,
                },
                {"id": "ga", "title": "Ga", "keys": ["ga"], "constant": True, "content": "Ga cũ."},
            ],
        }
    ).model_dump(mode="json")


@pytest.mark.parametrize("fmt", ["ccv2", "ccv3"])
@pytest.mark.parametrize("as_", ["json", "png"])
@pytest.mark.parametrize("with_book", [True, False])
def test_character_round_trip(fmt: Literal["ccv2", "ccv3"], as_: Literal["json", "png"], with_book: bool) -> None:
    card = _card()
    book = _book() if with_book else None
    body, mime, filename = export_character(
        card, fmt=fmt, as_=as_, avatar=None, lorebook=book, meta={"creator": "tester"}
    )
    assert filename.endswith(".png" if as_ == "png" else f".{fmt}.json")
    assert mime == ("image/png" if as_ == "png" else "application/json")
    result = import_file(body, filename)
    assert result.kind == "character"
    assert result.data == card
    assert result.lorebook == book
    assert result.needs_age is False
    assert (result.avatar is not None) == (as_ == "png")


def test_vietrp_json_round_trip() -> None:
    card = _card()
    body, _mime, filename = export_character(card, fmt="vietrp", as_="json", avatar=None, lorebook=None, meta={})
    assert filename == "tran-ha.card.json"
    assert import_file(body, filename).data == card


def test_round_trip_keeps_missing_age() -> None:
    card = _card()
    card["age"] = None
    body, _m, name = export_character(card, fmt="ccv3", as_="json", avatar=None, lorebook=None, meta={})
    result = import_file(body, name)
    assert result.data == card
    assert result.needs_age is True


def test_st_fields_are_composed() -> None:
    body, _m, _n = export_character(_card(), fmt="ccv2", as_="json", avatar=None, lorebook=_book(), meta={})
    obj = json.loads(body)
    data = obj["data"]
    assert obj["spec"] == "chara_card_v2"
    assert data["first_mes"] == "Chào."
    assert data["alternate_greetings"] == ["Lại là cậu à?", "Vào đi."]
    assert data["mes_example"].startswith("<START>\n{{user}}: Chào")
    assert data["scenario"] == "Văn phòng thám tử"
    assert data["personality"] == "Lạnh lùng nhưng tốt bụng."
    assert "Tuổi: 24" in data["description"]
    assert data["tags"] == ["trinh-thám", "hiện-đại"]
    assert len(data["character_book"]["entries"]) == 2
    assert data["extensions"]["vietrp"]["card"]["name"] == "Trần Hạ"


def test_ccv3_fields() -> None:
    body, _m, _n = export_character(_card(), fmt="ccv3", as_="json", avatar=None, lorebook=None, meta={})
    obj = json.loads(body)
    assert obj["spec"] == "chara_card_v3"
    assert obj["spec_version"] == "3.0"
    assert obj["data"]["group_only_greetings"] == []


def test_png_has_both_chunks() -> None:
    body, _m, _n = export_character(_card(), fmt="ccv3", as_="png", avatar=placeholder_png(), lorebook=None, meta={})
    assert set(read_text_chunks(body)) == {"chara", "ccv3"}


def test_png_rejects_non_png_avatar() -> None:
    with pytest.raises(FormatError) as exc:
        export_character(_card(), fmt="ccv2", as_="png", avatar=b"\xff\xd8jpeg", lorebook=None, meta={})
    assert exc.value.code == "avatar_not_png"


def test_vietrp_png_unsupported() -> None:
    with pytest.raises(FormatError) as exc:
        export_character(_card(), fmt="vietrp", as_="png", avatar=None, lorebook=None, meta={})
    assert exc.value.code == "export_unsupported"


def test_world_round_trip() -> None:
    world = {
        "format": "vietrp-world",
        "spec_version": "1.0",
        "name": "Sài Gòn Mơ",
        "rules": "Không phép thuật.",
        "tags": ["hiện-đại"],
        "lorebook_ids": [],
        "locations": [{"id": "vn", "parent_id": None, "level": "country", "name": "Việt Nam", "description": ""}],
        "openings": [],
    }
    body, mime, filename = export_world(world, meta={})
    assert (mime, filename) == ("application/json", "sai-gon-mo.world.json")
    result = import_file(body, filename)
    assert result.kind == "world"
    assert result.data == json.loads(body)


@pytest.mark.parametrize("fmt", ["vietrp", "st"])
def test_lorebook_round_trip(fmt: Literal["vietrp", "st"]) -> None:
    book = _book()
    body, _m, filename = export_lorebook(book, fmt=fmt, meta={})
    result = import_file(body, filename)
    assert result.kind == "lorebook"
    assert result.data == book


def test_st_worldinfo_fields_without_extension() -> None:
    body, _m, _n = export_lorebook(_book(), fmt="st", meta={})
    obj = json.loads(body)
    first = obj["entries"]["0"]
    assert first["key"] == ["chợ"]
    assert first["keysecondary"] == ["đêm"]
    assert first["position"] == 1
    assert first["disable"] is True
    assert first["order"] == 3
    del obj["extensions"]
    imported = import_file(json.dumps(obj).encode(), "x.json")
    assert imported.data["entries"][0]["enabled"] is False
    assert imported.data["entries"][0]["selective"] is True


def test_damaged_extension_falls_back_to_st_fields() -> None:
    body, _m, _n = export_character(_card(), fmt="ccv2", as_="json", avatar=None, lorebook=None, meta={})
    obj = json.loads(body)
    obj["data"]["extensions"]["vietrp"]["card"] = {"name": ""}
    result = import_file(json.dumps(obj).encode(), "x.json")
    assert result.data["name"] == "Trần Hạ"
    assert result.data["age"] == 24
