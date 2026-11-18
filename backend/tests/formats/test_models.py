from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from app.formats.card import VietrpCard
from app.formats.lorebook import Lorebook
from app.formats.migrations import Migrator, migrate
from app.formats.persona import Persona
from app.formats.validate import (
    card_has_minor,
    is_nsfw_tagged,
    validate_card,
    validate_lorebook,
    validate_persona,
    validate_world,
)
from app.formats.world import VietrpWorld

CARD: dict[str, Any] = {"name": "Linh", "age": 20}

WORLD: dict[str, Any] = {
    "name": "Sai Gon",
    "locations": [
        {"id": "vn", "level": "country", "name": "Viet Nam"},
        {"id": "hcm", "parent_id": "vn", "level": "province", "name": "TP.HCM"},
        {"id": "q1", "parent_id": "hcm", "level": "district", "name": "Q.1"},
    ],
    "openings": [{"id": "o1", "location_id": "q1", "tension": 2}],
}


def world_with(locations: list[dict[str, Any]], openings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    data = copy.deepcopy(WORLD)
    data["locations"] = locations
    data["openings"] = openings or []
    return data


def test_card_valid_defaults() -> None:
    card, warnings = validate_card(CARD, allow_missing_age=False)
    assert card.format == "vietrp-card"
    assert card.spec_version == "1.0"
    assert card.is_fictional is True
    assert warnings == []


@pytest.mark.parametrize(
    "patch",
    [
        {"name": ""},
        {"name": "x" * 81},
        {"age": -1},
        {"age": 10001},
        {"is_fictional": False},
        {"tagline": "x" * 141},
        {"tags": ["Upper"]},
        {"tags": ["x"] * 21},
        {"tags": ["x" * 33]},
        {"secrets": [{"id": "Bad Id", "content": "c"}]},
        {"extras": {"BAD": "v"}},
        {"unknown_key": 1},
    ],
)
def test_card_invalid(patch: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        VietrpCard.model_validate({**CARD, **patch})


def test_card_age_required_unless_import() -> None:
    with pytest.raises(ValueError):
        validate_card({"name": "A"}, allow_missing_age=False)
    with pytest.raises(ValueError):
        validate_card({"name": "A", "age": None}, allow_missing_age=False)
    card, warnings = validate_card({"name": "A"}, allow_missing_age=True)
    assert card.age is None
    assert [w.code for w in warnings] == ["age_missing"]


def test_card_warnings() -> None:
    data = {**CARD, "appearance": "x" * 301, "personality": "Hãy đóng vai Linh", "goals": "Bạn là Linh"}
    _, warnings = validate_card(data, allow_missing_age=False)
    pairs = {(w.path, w.code) for w in warnings}
    assert pairs == {
        ("appearance", "field_long"),
        ("personality", "imperative_text"),
        ("goals", "imperative_text"),
    }


def test_card_has_minor_and_nsfw() -> None:
    assert card_has_minor(VietrpCard(name="A", age=17))
    assert not card_has_minor(VietrpCard(name="A", age=18))
    assert not card_has_minor(VietrpCard(name="A", age=None))
    assert is_nsfw_tagged(["a", "nsfw"])
    assert not is_nsfw_tagged(["a"])


def test_world_valid() -> None:
    world, warnings = validate_world(WORLD)
    assert isinstance(world, VietrpWorld)
    assert warnings == []


def test_world_duplicate_location_id() -> None:
    locs = [
        {"id": "a", "level": "country", "name": "A"},
        {"id": "a", "level": "country", "name": "B"},
    ]
    with pytest.raises(ValidationError, match="duplicate location"):
        validate_world(world_with(locs))


def test_world_missing_parent() -> None:
    locs = [{"id": "a", "parent_id": "zz", "level": "country", "name": "A"}]
    with pytest.raises(ValidationError, match="does not exist"):
        validate_world(world_with(locs))


def test_world_cycle_rejected() -> None:
    locs = [
        {"id": "a", "parent_id": "b", "level": "country", "name": "A"},
        {"id": "b", "parent_id": "a", "level": "province", "name": "B"},
    ]
    with pytest.raises(ValidationError):
        validate_world(world_with(locs))


def test_world_self_parent_rejected() -> None:
    locs = [{"id": "a", "parent_id": "a", "level": "country", "name": "A"}]
    with pytest.raises(ValidationError):
        validate_world(world_with(locs))


@pytest.mark.parametrize("child_level", ["country", "planet"])
def test_world_level_order(child_level: str) -> None:
    locs = [
        {"id": "a", "level": "country", "name": "A"},
        {"id": "b", "parent_id": "a", "level": child_level, "name": "B"},
    ]
    with pytest.raises(ValidationError, match="deeper"):
        validate_world(world_with(locs))


def test_world_opening_location_must_exist() -> None:
    locs = [{"id": "a", "level": "country", "name": "A"}]
    with pytest.raises(ValidationError, match="location zz"):
        validate_world(world_with(locs, [{"id": "o", "location_id": "zz"}]))


def test_world_tension_range() -> None:
    locs = [{"id": "a", "level": "country", "name": "A"}]
    with pytest.raises(ValidationError):
        validate_world(world_with(locs, [{"id": "o", "location_id": "a", "tension": 5}]))


def test_persona() -> None:
    persona, warnings = validate_persona({"name": "Nam", "appearance": "Hãy tưởng tượng"})
    assert isinstance(persona, Persona)
    assert [w.code for w in warnings] == ["imperative_text"]
    with pytest.raises(ValidationError):
        validate_persona({"name": ""})


def test_lorebook_defaults_and_invalid() -> None:
    book, _ = validate_lorebook({"name": "L", "entries": [{"id": "e1", "content": "x"}]})
    assert isinstance(book, Lorebook)
    assert book.scan_depth == 50
    assert book.token_budget == 500
    assert book.entries[0].select_mode == "keyword"
    assert book.entries[0].position == "before_char"
    with pytest.raises(ValidationError):
        validate_lorebook({"name": "L", "entries": [{"id": "e1", "select_mode": "bogus"}]})
    with pytest.raises(ValidationError, match="duplicate"):
        validate_lorebook({"name": "L", "entries": [{"id": "e1"}, {"id": "e1"}]})


def test_migrate_registry() -> None:
    def fake_09_to_10(data: dict[str, Any]) -> dict[str, Any]:
        out = dict(data)
        out["name"] = out.pop("title")
        out["spec_version"] = "1.0"
        return out

    registry: dict[tuple[str, str], Migrator] = {("vietrp-card", "0.9"): fake_09_to_10}
    migrated = migrate("vietrp-card", {"title": "Old", "spec_version": "0.9"}, registry=registry)
    assert migrated == {"name": "Old", "spec_version": "1.0"}
    # Current version passes through untouched.
    assert migrate("vietrp-card", CARD) == CARD
    with pytest.raises(ValueError, match="no migration path"):
        migrate("vietrp-card", {"spec_version": "0.8"}, registry=registry)
    with pytest.raises(ValueError, match="no migration path"):
        migrate("vietrp-world", {"spec_version": "0.9"}, registry=registry)


@pytest.mark.parametrize(
    "tag",
    [
        "nsfw ",
        " nsfw",
        "nsfw\u200b",
        "\u200bnsfw",
        "ｎｓｆｗ",
        "nsfw_extreme",
        "nsfw-x",
        "18+",
        "r18",
        "r-18",
        "adult",
        "ns\u2060fw",
    ],
)
def test_is_nsfw_tagged_variants(tag: str) -> None:
    assert is_nsfw_tagged([tag])
    assert is_nsfw_tagged(["slice", tag])


def test_is_nsfw_tagged_negatives() -> None:
    assert not is_nsfw_tagged(["slice", "fantasy", "adulting", "18"])


def test_card_tags_are_normalized() -> None:
    card = VietrpCard.model_validate({**CARD, "tags": ["nsfw ", "ｎｓｆｗ", "ab\u200b c", "  two   words "]})
    assert card.tags == ["nsfw", "nsfw", "ab c", "two words"]
    assert is_nsfw_tagged(card.tags)


@pytest.mark.parametrize("tags", [["\u200b"], ["   "], ["Upper"], ["ＮＳＦＷ"]])
def test_card_and_world_reject_bad_tags(tags: list[str]) -> None:
    with pytest.raises(ValidationError):
        VietrpCard.model_validate({**CARD, "tags": tags})
    with pytest.raises(ValidationError):
        VietrpWorld.model_validate({**WORLD, "tags": tags})


def test_world_tags_are_normalized() -> None:
    world = VietrpWorld.model_validate({**WORLD, "tags": ["nsfw\u200b", "ｎｓｆｗ "]})
    assert world.tags == ["nsfw", "nsfw"]
