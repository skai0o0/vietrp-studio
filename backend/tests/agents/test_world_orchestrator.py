from __future__ import annotations

import uuid

from app.agents.base import AgentContext
from app.agents.orchestrator import (
    CORE_CARD_FIELDS,
    NARRATOR_ID,
    AgentConfig,
    WorldOrchestratorInput,
    build_world_questions,
    build_world_state,
    interpret_world,
    mentioned,
    nearby_locations,
    run_world,
)
from app.core.config import ADDRESS_CONFIDENCE, ARRIVE_THRESHOLD, CHAIN_THRESHOLD, QUIET_THRESHOLD, QUIET_TURNS
from app.formats.card import Secret, VietrpCard
from app.formats.lorebook import LorebookEntry
from app.formats.world import Location, Opening, VietrpWorld
from app.llm.decisions import ChoiceAnswer, DecisionResult, NoulAnswer
from app.llm.deps import LLMServices
from app.llm.fake import RecordedLLM
from app.llm.usage import Usage
from app.pipeline.lorebook import LoreHit
from app.pipeline.world_assembly import WorldCastEntry
from app.schemas.world_state import WorldState
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _world(name: str = "Sài Gòn Mưa") -> VietrpWorld:
    return VietrpWorld(
        name=name,
        locations=[
            Location(id="earth", parent_id=None, level="planet", name="Trái Đất"),
            Location(id="vn", parent_id="earth", level="country", name="Việt Nam"),
            Location(id="hcm", parent_id="vn", level="province", name="TP.HCM"),
            Location(id="hn", parent_id="vn", level="province", name="Hà Nội"),
            Location(id="khu_a", parent_id="hcm", level="district", name="Khu A"),
            Location(id="khu_b", parent_id="hcm", level="district", name="Khu B"),
            Location(id="can_tin", parent_id="khu_a", level="place", name="Căn tin"),
            Location(id="san_thuong", parent_id="khu_a", level="place", name="Sân thượng"),
            Location(id="thu_vien", parent_id="khu_b", level="place", name="Thư viện"),
        ],
        openings=[
            Opening(id="op1", title="Trưa", message="Trời nắng nhẹ.", location_id="can_tin", present_ids=["vy", "han"])
        ],
    )


def _cast() -> list[WorldCastEntry]:
    return [
        WorldCastEntry(
            "vy",
            VietrpCard(
                name="Trần Hạ Vy",
                age=20,
                aliases=["Lớp phó"],
                tagline="Lớp phó năng động",
                appearance="tóc đuôi ngựa",
                backstory="lớn lên ở Sài Gòn",
                secrets=[Secret(id="s1", content="sắp chuyển trường", reveal_when="khi tin tưởng")],
            ),
        ),
        WorldCastEntry(
            "han",
            VietrpCard(
                name="Nguyễn Gia Hân",
                age=21,
                tagline="Thư viện trưởng",
                appearance="đeo kính",
                backstory="thích đọc trinh thám",
                secrets=[Secret(id="s1", content="giữ chìa khóa phòng kho", reveal_when="khi bị hỏi thẳng")],
            ),
        ),
        WorldCastEntry(
            "tuan",
            VietrpCard(
                name="Lê Minh Tuấn",
                age=21,
                aliases=["Đội trưởng"],
                tagline="Đội trưởng bóng rổ",
            ),
        ),
    ]


def _hit(entry_id: str) -> LoreHit:
    entry = LorebookEntry(id=entry_id, title=entry_id, content=f"nội dung {entry_id}")
    return LoreHit(uuid.uuid4(), entry, 8, "candidate")


def _input(
    *,
    world_name: str = "Sài Gòn Mưa",
    present_ids: list[str] | None = None,
    silence: dict[str, int] | None = None,
    awaiting_reply: list[str] | None = None,
    user_message: str = "Vy ơi, hôm nay căn tin có món gì?",
    recent_user_messages: tuple[str, ...] = (),
    candidates: list[LoreHit] | None = None,
    chain_max: int = 3,
    force_speaker: str | None = None,
    location_id: str = "khu_a",
) -> WorldOrchestratorInput:
    return WorldOrchestratorInput(
        world=_world(world_name),
        cast=_cast(),
        state=WorldState(
            location_id=location_id,
            time="11:30 Thứ Hai",
            tension=1,
            present_ids=["vy", "han"] if present_ids is None else present_ids,
            silence=silence or {},
            awaiting_reply=awaiting_reply or [],
        ),
        user_name="Nam",
        user_message=user_message,
        recent=["Nam: chào mọi người", "Vy: chào cậu"],
        recent_user_messages=recent_user_messages,
        candidates=[_hit("can_tin"), _hit("san_thuong")] if candidates is None else candidates,
        chain_max=chain_max,
        force_speaker=force_speaker,
    )


def _ctx(llm: RecordedLLM, *, budget: int = 40) -> tuple[AgentContext, LLMServices]:
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(
        vault_id=gateway.vault_id,
        chat_id=gateway.chat_id,
        llm=gateway,
        settings=make_settings(decisions_max_questions=budget),
    )
    return ctx, services


def _decision(answers: dict[str, ChoiceAnswer | NoulAnswer]) -> DecisionResult:
    return DecisionResult(answers=answers, usage=Usage(prompt_tokens=100, completion_tokens=10), model="m")


def test_nearby_locations_returns_only_current_parent_siblings_and_children() -> None:
    locs = _world().locations
    nearby_khu_a = [loc.id for loc in nearby_locations(locs, "khu_a")]
    assert set(nearby_khu_a) == {"khu_a", "hcm", "khu_b", "can_tin", "san_thuong"}
    assert "earth" not in nearby_khu_a
    assert "vn" not in nearby_khu_a
    assert "hn" not in nearby_khu_a
    assert "thu_vien" not in nearby_khu_a
    assert len(nearby_khu_a) == len(set(nearby_khu_a))

    # Root siblings sharing parent_id=None
    roots = [
        Location(id="p1", parent_id=None, level="planet", name="Hành tinh 1"),
        Location(id="p2", parent_id=None, level="planet", name="Hành tinh 2"),
        Location(id="c1", parent_id="p1", level="country", name="Nước 1"),
        Location(id="c2", parent_id="p2", level="country", name="Nước 2"),
    ]
    assert {loc.id for loc in nearby_locations(roots, "p1")} == {"p1", "p2", "c1"}
    assert nearby_locations(locs, "missing") == []


def test_mentioned_matches_aliases_and_last_word_with_word_boundaries() -> None:
    vy = VietrpCard(name="Trần Hạ Vy", age=20, aliases=["Lớp phó"])
    assert mentioned(vy, "Vy ơi lại đây")
    assert mentioned(vy, "Chào lớp phó nhé!")
    assert not mentioned(vy, "Vỹ đang đi bộ")
    assert not mentioned(vy, "Tuy vậy vẫn ổn")

    han = VietrpCard(name="Nguyễn Gia Hân", age=21)
    assert mentioned(han, "Hân, cậu xong chưa?")
    assert not mentioned(han, "Thân thiện quá")


def test_build_world_questions_enforces_budget_and_nearby_context() -> None:
    inp = _input(silence={"han": 3, "vy": 1}, recent_user_messages=("Gọi Tuấn vào đi!",))
    questions = build_world_questions(AgentConfig(), inp, budget=40)
    assert "turn_type" in questions and "speaker" in questions and "addressee" in questions
    # tuan is mention-arriving so tuan is a candidate speaker (gets followup__), not in remaining_absent arrive__
    assert "arrive__tuan" not in questions
    assert "followup__tuan" in questions and "followup__vy" in questions
    assert "field__vy__backstory" in questions and "secret__vy__s1" in questions
    assert "lore__can_tin" in questions

    # Strict budget caps at any small limit
    for cap in (0, 2, 5, 8):
        capped = build_world_questions(AgentConfig(), inp, budget=cap)
        assert len(capped) == cap

    # chain_max=1 omits followup__ questions
    no_chain = build_world_questions(AgentConfig(), _input(chain_max=1), budget=40)
    assert not any(k.startswith("followup__") for k in no_chain)

    # build_world_state only shows nearby locations and surfaces silence >= 2
    state_dict = build_world_state(AgentConfig(), inp)
    assert "TP.HCM › Khu A" in state_dict["world_context"]
    assert "Căn tin" in state_dict["world_context"]
    assert "Thư viện" not in state_dict["world_context"]  # cousin excluded
    assert "Hà Nội" not in state_dict["world_context"]  # aunt excluded
    assert "Nguyễn Gia Hân: có mặt 3 lượt" in state_dict["silence_notes"]
    assert "Trần Hạ Vy" not in state_dict["silence_notes"]


async def test_run_world_happy_path_multi_speaker_plan() -> None:
    ctx, services = _ctx(RecordedLLM.from_dir(names=["world_orchestrator_ok.json", "wiring_models.json"]))
    try:
        result = await run_world(ctx, AgentConfig(), _input())
    finally:
        await services.aclose()
    plan = result.value
    assert not plan.fallback and result.notices == []
    assert plan.turn_type == "dialogue"
    assert plan.arriving_ids == ["tuan"]
    assert plan.addressee == "vy"
    assert plan.lore_entry_ids == ["can_tin"]
    assert [sp.id for sp in plan.speakers] == ["vy", "tuan", "han"]
    assert [sp.order for sp in plan.speakers] == [0, 1, 2]
    assert plan.speakers[0].card_fields == [*CORE_CARD_FIELDS, "backstory", "secrets"]
    assert plan.speakers[0].secret_ids == ["s1"]
    assert plan.speakers[1].entering is True
    assert plan.speakers[2].entering is False and plan.speakers[2].secret_ids == []

    event = plan.to_event()
    assert [sp.id for sp in event.speakers] == ["vy", "tuan", "han"]
    assert event.speakers[1].order == 1 and event.speakers[1].reason == "arriving"
    assert event.lore_ids == ["can_tin"]


async def test_run_world_arriving_override_and_fallback() -> None:
    # Narrator chosen by Decisions, but tuan is mention-arriving and user spoke -> arriving overrides narrator
    ctx, services = _ctx(
        RecordedLLM.from_dir(names=["world_orchestrator_narrator_override.json", "wiring_models.json"])
    )
    try:
        result = await run_world(
            ctx,
            AgentConfig(),
            _input(
                world_name="Khu KTX",
                present_ids=["vy"],
                user_message="Tuấn tới cửa rồi kìa, vào đi!",
                candidates=[],
            ),
        )
    finally:
        await services.aclose()
    plan = result.value
    assert plan.speakers[0].id == "tuan" and plan.speakers[0].entering is True
    assert plan.speakers[0].reason == "arriving"

    # Error path returns narrator-only fallback + orchestrator_fallback notice
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([{"status": 500, "json": {"error": {"message": "down"}}}], {"path": "/api/alpha/decisions"})
    f_ctx, f_services = _ctx(llm)
    try:
        fallback_res = await run_world(f_ctx, AgentConfig(), _input())
    finally:
        await f_services.aclose()
    assert fallback_res.value.fallback is True
    assert [sp.id for sp in fallback_res.value.speakers] == [NARRATOR_ID]
    assert fallback_res.value.speakers[0].kind == "narrator"
    assert [n.code for n in fallback_res.notices] == ["orchestrator_fallback"]


def test_interpret_world_overrides_owed_force_and_chain_cap() -> None:
    # 1. Addressee override + absent addressee added to arriving_ids + owed excludes primary speaker
    inp_addr = _input(user_message="Cậu ơi, Tuấn với Hân đâu rồi?", chain_max=2)
    dec_addr = _decision(
        {
            "turn_type": ChoiceAnswer(choice="dialogue", confidence=0.8, probabilities={"dialogue": 0.8}),
            "speaker": ChoiceAnswer(choice="vy", confidence=0.7, probabilities={"vy": 0.7, "han": 0.2}),
            "addressee": ChoiceAnswer(
                choice="han", confidence=ADDRESS_CONFIDENCE, probabilities={"han": 0.6, "vy": 0.3, "group": 0.1}
            ),
            "arrive__tuan": NoulAnswer(p=ARRIVE_THRESHOLD),
        }
    )
    plan_addr = interpret_world(AgentConfig(), inp_addr, dec_addr)
    assert plan_addr.addressee == "han"
    assert plan_addr.speakers[0].id == "han" and plan_addr.speakers[0].reason == "addressee"
    assert "tuan" in plan_addr.arriving_ids
    assert [sp.id for sp in plan_addr.speakers] == ["han", "tuan"]  # capped at chain_max=2

    # 2. Named fallback when speaker conf < 0.6 and group prob < 0.5
    inp_named = _input(user_message="Hân nghĩ sao?", chain_max=1)
    dec_named = _decision(
        {
            "turn_type": ChoiceAnswer(choice="dialogue", confidence=0.8, probabilities={"dialogue": 0.8}),
            "speaker": ChoiceAnswer(choice="vy", confidence=0.45, probabilities={"vy": 0.45, "han": 0.4}),
            "addressee": ChoiceAnswer(choice="group", confidence=0.4, probabilities={"group": 0.4, "han": 0.4}),
        }
    )
    plan_named = interpret_world(AgentConfig(), inp_named, dec_named)
    assert plan_named.speakers[0].id == "han" and plan_named.speakers[0].reason == "named"
    assert len(plan_named.speakers) == 1

    # Named fallback does NOT trigger when group prob >= 0.5
    dec_group = _decision(
        {
            "turn_type": ChoiceAnswer(choice="dialogue", confidence=0.8, probabilities={"dialogue": 0.8}),
            "speaker": ChoiceAnswer(choice="vy", confidence=0.45, probabilities={"vy": 0.45, "han": 0.4}),
            "addressee": ChoiceAnswer(choice="group", confidence=0.55, probabilities={"group": 0.55, "han": 0.3}),
        }
    )
    assert interpret_world(AgentConfig(), inp_named, dec_group).speakers[0].id == "vy"

    # 3. force_speaker overrides when present or narrator, not when absent
    dec_vy = _decision(
        {
            "turn_type": ChoiceAnswer(choice="dialogue", confidence=0.9, probabilities={"dialogue": 0.9}),
            "speaker": ChoiceAnswer(choice="vy", confidence=0.95, probabilities={"vy": 0.95}),
            "addressee": ChoiceAnswer(choice="vy", confidence=0.9, probabilities={"vy": 0.9}),
        }
    )
    forced_nar = interpret_world(AgentConfig(), _input(force_speaker="narrator", chain_max=1), dec_vy)
    assert forced_nar.speakers[0].id == NARRATOR_ID and forced_nar.speakers[0].reason == "forced"
    assert forced_nar.owed_ids == ["vy"]  # vy was addressed by user, excluded only when vy is primary

    ignored_absent = interpret_world(AgentConfig(), _input(force_speaker="tuan", chain_max=1), dec_vy)
    assert ignored_absent.speakers[0].id == "vy"

    # 4. Continue turn (user_message="") carries state.awaiting_reply + long-silent quiet threshold
    inp_cont = _input(
        user_message="",
        present_ids=["vy", "han"],
        silence={"han": QUIET_TURNS},
        awaiting_reply=["han"],
        chain_max=3,
    )
    dec_cont = _decision(
        {
            "turn_type": ChoiceAnswer(choice="dialogue", confidence=0.8, probabilities={"dialogue": 0.8}),
            "speaker": ChoiceAnswer(choice="vy", confidence=0.7, probabilities={"vy": 0.7, "han": 0.35}),
            "followup__han": NoulAnswer(p=QUIET_THRESHOLD),
        }
    )
    plan_cont = interpret_world(AgentConfig(), inp_cont, dec_cont)
    assert plan_cont.owed_ids == ["han"]
    assert [sp.id for sp in plan_cont.speakers] == ["vy", "han"]

    # 5. Chain order: long-silent quiet_followup + normal CHAIN_THRESHOLD + strong secondary, deduplicated & capped
    inp_chain = _input(
        user_message="Mọi người sao thế?",
        present_ids=["vy", "han"],
        silence={"han": QUIET_TURNS},
        chain_max=3,
    )
    dec_chain = _decision(
        {
            "turn_type": ChoiceAnswer(choice="dialogue", confidence=0.8, probabilities={"dialogue": 0.8}),
            "speaker": ChoiceAnswer(choice="vy", confidence=0.65, probabilities={"vy": 0.65, "han": 0.25}),
            "addressee": ChoiceAnswer(choice="group", confidence=0.7, probabilities={"group": 0.7}),
            "followup__han": NoulAnswer(p=QUIET_THRESHOLD),
            "arrive__tuan": NoulAnswer(p=CHAIN_THRESHOLD),
        }
    )
    plan_chain = interpret_world(AgentConfig(), inp_chain, dec_chain)
    assert [sp.id for sp in plan_chain.speakers] == ["vy", "tuan", "han"]
    assert [sp.reason for sp in plan_chain.speakers] == ["orchestrator", "arriving", "quiet_followup"]
