from __future__ import annotations

from app.agents import bond_drafter as drafter
from app.agents import bond_selector as selector
from app.agents.base import AgentContext
from app.formats.card import Addressing, Relationships, VietrpCard
from app.formats.persona import Persona
from app.llm.fake import RecordedLLM
from app.pipeline.world_assembly import WorldCastEntry
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _cast() -> list[WorldCastEntry]:
    return [
        WorldCastEntry(
            "vy",
            VietrpCard(
                name="Vy",
                age=20,
                tagline="Lớp phó năng động",
                addressing=Addressing(user="tôi - cậu", by_character={"han": "mày - tao"}),
                relationships=Relationships(by_character={"han": "bạn thân từ nhỏ"}),
            ),
        ),
        WorldCastEntry(
            "han",
            VietrpCard(
                name="Hân",
                age=21,
                tagline="Thư viện trưởng trầm tĩnh",
                relationships=Relationships(user="bạn cùng bàn"),
            ),
        ),
    ]


def test_world_pairs_builds_user_and_ordered_character_pairs_with_pinned_fields() -> None:
    cast = [
        *_cast(),
        WorldCastEntry("tuan", VietrpCard(name="Tuấn", age=21, tagline="Đội trưởng bóng rổ")),
    ]
    pairs = drafter.world_pairs(cast, Persona(name="Nam", age=21, gender="nam"), "người chơi")
    # 3 user pairs + 3*2 character pairs = 9
    assert [p.pair_id for p in pairs] == [
        "vy:user",
        "han:user",
        "tuan:user",
        "vy:han",
        "vy:tuan",
        "han:vy",
        "han:tuan",
        "tuan:vy",
        "tuan:han",
    ]
    by_id = {p.pair_id: p for p in pairs}
    assert by_id["vy:user"].pinned == {"addressing": "tôi - cậu"}
    assert by_id["han:user"].pinned == {"relationship": "bạn cùng bàn"}
    assert by_id["vy:han"].other_kind == "character"
    assert by_id["vy:han"].other_brief == "Thư viện trưởng trầm tĩnh"
    assert by_id["vy:han"].pinned == {"addressing": "mày - tao", "relationship": "bạn thân từ nhỏ"}
    assert by_id["han:vy"].pinned == {}


async def test_world_bonds_draft_select_merge_preserves_pinned_by_character_and_filters_views() -> None:
    pairs = drafter.world_pairs(_cast(), Persona(name="Nam", age=21), "người chơi")
    gateway, services, _, _ = make_gateway(
        RecordedLLM.from_dir(names=["world_bond_drafter_ok.json", "world_bond_selector_ok.json", "wiring_models.json"])
    )
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=gateway.chat_id, llm=gateway, settings=make_settings())
    try:
        drafted = await drafter.run(ctx, drafter.AgentConfig(), drafter.DrafterInput(pairs, "Cả nhóm ngồi ở căn tin."))
        picked = await selector.run(ctx, selector.AgentConfig(), selector.SelectorInput(pairs, drafted.value))
    finally:
        await services.aclose()

    assert drafted.notices == [] and picked.notices == []
    assert set(picked.value) == {"vy:user", "han:user", "vy:han", "han:vy"}
    # bond__1 chose option 2 ("em - anh"), bond__3 chose option 2 ("bà - tui")
    assert picked.value["han:user"].addressing == "em - anh"
    assert picked.value["han:vy"].addressing == "bà - tui"

    records = selector.apply_selection({}, pairs, picked.value, seq=0)
    # Pinned by_character values on vy:han MUST win over drafted "mày - tao (muốn ghi đè)" / "bạn thân (muốn ghi đè)"
    assert records["vy:han"].fields.addressing == "mày - tao"
    assert records["vy:han"].fields.relationship == "bạn thân từ nhỏ"
    assert records["vy:han"].fields.nickname == "Hân mọt sách"
    assert records["vy:han"].pinned == ["addressing", "relationship"]

    # bonds_for_speaker filters to speaker + present cast and skips pinned fields
    extra_cast = [
        *_cast(),
        WorldCastEntry("tuan", VietrpCard(name="Tuấn", age=21)),
    ]
    all_pairs = drafter.world_pairs(extra_cast, Persona(name="Nam", age=21), "người chơi")
    with_absent = selector.apply_selection(
        records,
        all_pairs,
        {"vy:tuan": drafter.BondFields(addressing="cậu - tớ", closeness=2)},
        seq=0,
    )
    vy_present_views = drafter.bonds_for_speaker(with_absent, "vy", present_ids=["vy", "han"])
    pair_labels = {v.pair for v in vy_present_views}
    assert pair_labels == {"Vy ↔ Nam", "Vy ↔ Hân", "Hân ↔ Vy"}
    vy_han_view = next(v for v in vy_present_views if v.pair == "Vy ↔ Hân")
    assert "addressing" not in vy_han_view.fields and "relationship" not in vy_han_view.fields
    assert vy_han_view.fields["nickname"] == "Hân mọt sách"

    # Narrator/group sees all active pairs among present_ids + user (not absent tuan)
    narrator_views = drafter.bonds_for_speaker(with_absent, "narrator", present_ids=["vy", "han"])
    assert {v.pair for v in narrator_views} == {"Vy ↔ Nam", "Hân ↔ Nam", "Vy ↔ Hân", "Hân ↔ Vy"}


async def test_bond_selector_respects_decisions_budget_with_first_option_fallback() -> None:
    pairs = drafter.world_pairs(_cast(), Persona(name="Nam", age=21), "người chơi")
    # Build drafted options directly (2 options each for 4 pairs)
    drafted = drafter.DraftedBonds(
        options={
            p.pair_id: [
                drafter.BondFields(addressing="option1", closeness=1),
                drafter.BondFields(addressing="option2", closeness=3),
            ]
            for p in pairs
        }
    )
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add(
        [
            {
                "status": 200,
                "json": {
                    "model": "microsoft/microsoft-decision-1",
                    "usage": {"prompt_tokens": 100, "completion_tokens": 4},
                    "answers": {
                        "bond__0": {"choice": "2", "confidence": 0.9, "probabilities": {"1": 0.1, "2": 0.9}},
                        "bond__1": {"choice": "2", "confidence": 0.9, "probabilities": {"1": 0.1, "2": 0.9}},
                    },
                },
            }
        ],
        {"path": "/api/alpha/decisions"},
    )
    gateway, services, _, _ = make_gateway(llm)
    # Budget is 2, so bond__2 and bond__3 are NOT asked and must fall back to option 1!
    ctx = AgentContext(
        vault_id=gateway.vault_id,
        chat_id=gateway.chat_id,
        llm=gateway,
        settings=make_settings(decisions_max_questions=2),
    )
    try:
        picked = await selector.run(ctx, selector.AgentConfig(), selector.SelectorInput(pairs, drafted))
    finally:
        await services.aclose()
    assert picked.value["vy:user"].addressing == "option2"
    assert picked.value["han:user"].addressing == "option2"
    assert picked.value["vy:han"].addressing == "option1"
    assert picked.value["han:vy"].addressing == "option1"
    assert len(selector.build_questions(selector.AgentConfig(), selector.SelectorInput(pairs, drafted), 2)) == 2
