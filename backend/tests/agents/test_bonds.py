from __future__ import annotations

from app.agents import bond_drafter as drafter
from app.agents import bond_selector as selector
from app.agents.base import AgentContext, AgentResult
from app.formats.card import Addressing, VietrpCard
from app.formats.persona import Persona
from app.llm.fake import RecordedLLM
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _pair(card: VietrpCard, cid: str = "mai") -> drafter.BondPair:
    return drafter.user_pair(card, cid, Persona(name="Nam", age=22), "người chơi")


async def _run_drafter(fixture: str, pair: drafter.BondPair) -> AgentResult[drafter.DraftedBonds]:
    gateway, services, _, _ = make_gateway(RecordedLLM.from_dir(names=[fixture, "wiring_models.json"]))
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=gateway.chat_id, llm=gateway, settings=make_settings())
    try:
        return await drafter.run(ctx, drafter.AgentConfig(), drafter.DrafterInput([pair], "Mai chào Nam."))
    finally:
        await services.aclose()


async def _run_selector(
    llm: RecordedLLM, pair: drafter.BondPair, drafted: drafter.DraftedBonds
) -> AgentResult[dict[str, drafter.BondFields]]:
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=gateway.chat_id, llm=gateway, settings=make_settings())
    try:
        return await selector.run(ctx, selector.AgentConfig(), selector.SelectorInput([pair], drafted))
    finally:
        await services.aclose()


async def test_drafter_parses_options_and_clamps_closeness() -> None:
    pair = _pair(VietrpCard(name="Mai", age=20))
    result = await _run_drafter("bond_drafter_ok.json", pair)
    options = result.value.options["mai:user"]
    assert len(options) == 2  # the nonsense entry is dropped
    assert options[0].addressing == "anh - em" and options[0].closeness == 2
    assert options[1].closeness == 4  # 9 clamped to the 0-4 range
    assert result.notices == []


async def test_drafter_malformed_reply_gives_empty_options_and_notice() -> None:
    pair = drafter.BondPair("lan:user", "Lan", "Nam", "persona")
    result = await _run_drafter("bond_drafter_malformed.json", pair)
    assert result.value.options == {"lan:user": []}
    assert [n.code for n in result.notices] == ["bond_drafter_malformed"]


async def test_selector_picks_option_and_merge_never_overwrites_pinned_fields() -> None:
    card = VietrpCard(name="Mai", age=20, addressing=Addressing(user="anh - em ruột"))
    pair = _pair(card)
    drafted = (await _run_drafter("bond_drafter_ok.json", pair)).value
    picked = await _run_selector(
        RecordedLLM.from_dir(names=["bond_selector_ok.json", "wiring_models.json"]), pair, drafted
    )
    chosen = picked.value["mai:user"]
    assert chosen.addressing == "tôi - cậu" and chosen.relationship == "đồng nghiệp"

    records = selector.apply_selection({}, [pair], picked.value, seq=1)
    record = records["mai:user"]
    # The card pins addressing.user; the agent's "tôi - cậu" must not replace it.
    assert record.fields.addressing == "anh - em ruột" and record.pinned == ["addressing"]
    assert record.fields.relationship == "đồng nghiệp" and record.fields.closeness == 4
    assert {c.field for c in record.changes} >= {"addressing", "relationship", "closeness"}
    assert all(c.seq == 1 for c in record.changes)

    # A second merge only fills gaps; filled and pinned fields stay.
    first_option = drafted.options["mai:user"][0]
    again = selector.apply_selection(records, [pair], {"mai:user": first_option}, seq=5)["mai:user"]
    assert again.fields.relationship == "đồng nghiệp" and again.fields.stance == "lịch sự"
    assert again.fields.closeness == 4 and again.fields.addressing == "anh - em ruột"
    assert again.fields.nickname == "Bông"  # only the empty fields were filled
    assert [c.field for c in again.changes[len(record.changes) :]] == ["nickname", "history"]

    # A later Selector run (P4) may replace agent-written fields, never pinned or hand-edited ones.
    edited = record.model_copy(update={"manual": ["relationship"]})
    moved = selector.apply_selection(
        {"mai:user": edited}, [pair], {"mai:user": first_option}, seq=9, overwrite_unpinned=True
    )["mai:user"]
    assert moved.fields.addressing == "anh - em ruột" and moved.fields.relationship == "đồng nghiệp"
    assert moved.fields.nickname == "Bông" and moved.changes[-1].seq == 9


async def test_selector_failure_falls_back_to_first_option() -> None:
    pair = _pair(VietrpCard(name="Mai", age=20))
    drafted = (await _run_drafter("bond_drafter_ok.json", pair)).value
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([{"status": 400, "json": {"error": {"message": "bad"}}}], {"path": "/api/alpha/decisions"})
    picked = await _run_selector(llm, pair, drafted)
    assert picked.value["mai:user"] == drafted.options["mai:user"][0]
    assert [n.code for n in picked.notices] == ["bond_selector_fallback"]


def test_bond_views_skip_pinned_fields() -> None:
    record = drafter.BondRecord(
        pair_id="mai:user",
        label="Mai ↔ Nam",
        fields=drafter.BondFields(addressing="anh - em", relationship="bạn cũ"),
        pinned=["addressing"],
    )
    views = drafter.bond_views({"mai:user": record})
    assert len(views) == 1 and dict(views[0].fields) == {"relationship": "bạn cũ"}
