from __future__ import annotations

from app.agents import state_keeper
from app.agents.base import AgentContext
from app.core.config import (
    CHAIN_THRESHOLD,
    LOCATION_CONFIDENCE,
    OWED_THRESHOLD,
    PRESENCE_ENTER_THRESHOLD,
    PRESENCE_STAY_THRESHOLD,
    QUIET_THRESHOLD,
    QUIET_TURNS,
    TIME_CONFIDENCE,
)
from app.formats.card import VietrpCard
from app.formats.world import Location, Opening, VietrpWorld
from app.llm.decisions import ChoiceAnswer, DecisionResult, NoulAnswer, ScoreAnswer
from app.llm.deps import LLMServices
from app.llm.extractions import ExtractedValue, ExtractionResult
from app.llm.fake import RecordedLLM
from app.llm.usage import Usage
from app.pipeline.world_assembly import WorldCastEntry
from app.schemas.world_state import CharacterSceneState, SceneState, WorldState
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _world() -> VietrpWorld:
    return VietrpWorld(
        name="Sài Gòn Mưa",
        locations=[
            Location(id="earth", parent_id=None, level="planet", name="Trái Đất"),
            Location(id="hcm", parent_id="earth", level="province", name="TP.HCM"),
            Location(id="khu_a", parent_id="hcm", level="district", name="Khu A"),
            Location(id="can_tin", parent_id="khu_a", level="place", name="Căn tin"),
            Location(id="san_thuong", parent_id="khu_a", level="place", name="Sân thượng"),
            Location(id="khu_b", parent_id="hcm", level="district", name="Khu B"),
            Location(id="thu_vien", parent_id="khu_b", level="place", name="Thư viện"),
        ],
        openings=[Opening(id="op1", location_id="can_tin", present_ids=["vy", "han"])],
    )


def _cast() -> list[WorldCastEntry]:
    return [
        WorldCastEntry("vy", VietrpCard(name="Vy", age=20, tagline="Lớp phó")),
        WorldCastEntry("han", VietrpCard(name="Hân", age=21, tagline="Thư viện trưởng")),
        WorldCastEntry("tuan", VietrpCard(name="Tuấn", age=21, tagline="Đội trưởng")),
    ]


def _base_state() -> WorldState:
    return WorldState(
        location_id="can_tin",
        time="11:30 Thứ Hai",
        tension=1,
        present_ids=["vy", "han"],
        awaiting_reply=[],
        silence={"vy": 1, "han": 2},
        scene=SceneState(
            env={"weather": "mát"},
            chars={"vy": CharacterSceneState(mood="vui")},
            items=["ly trà sữa"],
        ),
        bonds={"vy:user": {"addressing": "tôi - cậu"}},
        npcs=[{"name": "Cô bán hàng", "age": 45}],
        summary="Cả nhóm vừa tan học.",
        summary_upto=4,
        events=[{"id": "ev1", "title": "Vy rủ đi ăn"}],
        manual=["tension"],
    )


def _input(
    *,
    state: WorldState | None = None,
    speakers_this_turn: tuple[str, ...] = ("vy",),
    owed_ids: tuple[str, ...] = ("han",),
    arriving_ids: tuple[str, ...] = (),
) -> state_keeper.StateKeeperInput:
    return state_keeper.StateKeeperInput(
        world=_world(),
        cast=_cast(),
        state=_base_state() if state is None else state,
        user_name="Nam",
        recent_lines=["Nam: Lên sân thượng không?", "Vy: Đi luôn cho mát."],
        speakers_this_turn=speakers_this_turn,
        owed_ids=owed_ids,
        arriving_ids=arriving_ids,
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


def test_keep_day_preserves_vietnamese_weekday_when_missing() -> None:
    assert state_keeper.keep_day("10:00 Thứ Hai", "12 giờ 30 trưa") == "12 giờ 30 trưa Thứ Hai"
    assert state_keeper.keep_day("Chiều thứ Bảy", "18:00") == "18:00 thứ Bảy"
    assert state_keeper.keep_day("Sáng chủ nhật", "11 giờ trưa") == "11 giờ trưa chủ nhật"
    assert state_keeper.keep_day("10:00 Thứ Hai", "08:00 Thứ Ba") == "08:00 Thứ Ba"
    assert state_keeper.keep_day("10:00", "11:00") == "11:00"
    assert state_keeper.keep_day("10:00 thứ Tư", "12:00") == "12:00 thứ Tư"


def test_build_questions_uses_nearby_locations_only_and_enforces_budget() -> None:
    inp = _input(speakers_this_turn=("vy", "tuan"))
    questions = state_keeper.build_questions(state_keeper.AgentConfig(), inp, budget=40)
    loc_q = questions["location"]
    assert loc_q.type == "choice"
    # Current=can_tin, parent=khu_a, sibling=san_thuong. Never hcm, khu_b, thu_vien, earth!
    assert set(loc_q.criteria.keys()) == {"can_tin", "khu_a", "san_thuong"}

    tens_q = questions["tension"]
    assert tens_q.type == "score" and len(tens_q.criteria) == 5

    # last_speaker="tuan" is excluded from interject__
    assert "interject__vy" in questions and "interject__han" in questions
    assert "interject__tuan" not in questions

    # Budget strictly enforced
    assert len(state_keeper.build_questions(state_keeper.AgentConfig(), inp, budget=4)) == 4
    assert state_keeper.build_questions(state_keeper.AgentConfig(), inp, budget=0) == {}


async def test_run_updates_state_with_hysteresis_and_preserves_other_fields() -> None:
    llm = RecordedLLM.from_dir(
        names=["state_keeper_decisions_ok.json", "state_keeper_time_ok.json", "wiring_models.json"]
    )
    ctx, services = _ctx(llm)
    try:
        result = await state_keeper.run(ctx, state_keeper.AgentConfig(), _input())
    finally:
        await services.aclose()
    assert result.notices == []
    out = result.value
    st = out.state

    # vy had 0.32 >= 0.2 (stay), han had 0.12 < 0.2 (leave), tuan had 0.68 >= 0.5 (enter)
    assert st.present_ids == ["vy", "tuan"]
    assert st.location_id == "san_thuong"
    assert st.tension == 3
    assert st.time == "12 giờ 30 trưa Thứ Hai"
    # tuan just entered and did not speak -> awaiting_reply & next_speaker=tuan ("arrived_silent")
    assert st.awaiting_reply == ["tuan"]
    assert st.silence == {"vy": 0, "tuan": 1}
    assert out.next_speaker == "tuan" and out.next_reason == "arrived_silent"

    assert set(out.changed) == {"present_ids", "location_id", "tension", "time", "awaiting_reply", "silence"}
    assert out.confidence["location_id"] == 0.85
    assert out.confidence["time"] == 0.9
    assert out.confidence["present__vy"] == 0.32

    # Preserved fields untouched
    base = _base_state()
    assert st.scene == base.scene
    assert st.bonds == base.bonds
    assert st.npcs == base.npcs
    assert st.summary == base.summary
    assert st.summary_upto == base.summary_upto
    assert st.events == base.events
    assert st.manual == base.manual


def test_interpret_thresholds_hysteresis_and_next_speaker_priority() -> None:
    # Arriving character uses stay threshold (0.2), absent below 0.5 does not enter
    inp = _input(
        state=WorldState(location_id="can_tin", time="09:00 Thứ Sáu", tension=0, present_ids=["vy"], silence={"vy": 0}),
        speakers_this_turn=("vy",),
        owed_ids=(),
        arriving_ids=("han",),
    )
    dec = DecisionResult(
        answers={
            "present__vy": NoulAnswer(p=PRESENCE_STAY_THRESHOLD),
            "present__han": NoulAnswer(p=PRESENCE_STAY_THRESHOLD),  # arriving uses 0.2
            "present__tuan": NoulAnswer(p=PRESENCE_ENTER_THRESHOLD - 0.05),  # absent needs 0.5
            # Out-of-neighborhood choice ignored even with high confidence!
            "location": ChoiceAnswer(choice="thu_vien", confidence=0.95, probabilities={"thu_vien": 0.95}),
            "tension": ScoreAnswer(score=0.2),
            "interject__han": NoulAnswer(p=0.1),
            "interject__tuan": NoulAnswer(p=0.9),
        },
        usage=Usage(),
        model="m",
    )
    ext = ExtractionResult(
        values={"time": ExtractedValue(value="10:00", confidence=TIME_CONFIDENCE - 0.05)}, usage=Usage(), model="m"
    )
    out = state_keeper.interpret(inp, dec, ext)
    assert out.state.present_ids == ["vy", "han"]
    assert out.state.location_id == "can_tin"  # out-of-neighborhood rejected
    assert out.state.time == "09:00 Thứ Sáu"  # below TIME_CONFIDENCE

    # Low location confidence ignored even if nearby
    dec_low_loc = DecisionResult(
        answers={
            "present__vy": NoulAnswer(p=0.9),
            "present__han": NoulAnswer(p=0.0),
            "present__tuan": NoulAnswer(p=0.0),
            "location": ChoiceAnswer(
                choice="san_thuong", confidence=LOCATION_CONFIDENCE - 0.05, probabilities={"san_thuong": 0.25}
            ),
            "tension": ScoreAnswer(score=0.0),
        },
        usage=Usage(),
        model="m",
    )
    assert state_keeper.interpret(inp, dec_low_loc, None).state.location_id == "can_tin"

    # Quiet character (silence >= QUIET_TURNS after +1) triggers at QUIET_THRESHOLD (0.35), owed triggers at 0.2
    inp_q = _input(
        state=WorldState(
            location_id="can_tin",
            time="09:00",
            present_ids=["vy", "han", "tuan"],
            silence={"vy": 0, "han": QUIET_TURNS - 1, "tuan": 0},
        ),
        speakers_this_turn=("vy",),
        owed_ids=(),
    )
    dec_q = DecisionResult(
        answers={
            "present__vy": NoulAnswer(p=0.9),
            "present__han": NoulAnswer(p=0.9),
            "present__tuan": NoulAnswer(p=0.9),
            "location": ChoiceAnswer(choice="can_tin", confidence=0.9, probabilities={"can_tin": 0.9}),
            "tension": ScoreAnswer(score=1.0),
            "interject__han": NoulAnswer(p=QUIET_THRESHOLD),
            "interject__tuan": NoulAnswer(p=CHAIN_THRESHOLD - 0.05),
        },
        usage=Usage(),
        model="m",
    )
    out_q = state_keeper.interpret(inp_q, dec_q, None)
    assert out_q.next_speaker == "han" and out_q.next_reason == "quiet_followup"

    # Owed reply priority beats normal interject when >= OWED_THRESHOLD
    inp_owed = _input(
        state=WorldState(location_id="can_tin", present_ids=["vy", "han", "tuan"]),
        speakers_this_turn=("vy",),
        owed_ids=("han",),
    )
    dec_owed = DecisionResult(
        answers={
            "present__vy": NoulAnswer(p=0.9),
            "present__han": NoulAnswer(p=0.9),
            "present__tuan": NoulAnswer(p=0.9),
            "location": ChoiceAnswer(choice="can_tin", confidence=0.9, probabilities={"can_tin": 0.9}),
            "tension": ScoreAnswer(score=1.0),
            "interject__han": NoulAnswer(p=OWED_THRESHOLD),
            "interject__tuan": NoulAnswer(p=0.9),
        },
        usage=Usage(),
        model="m",
    )
    out_owed = state_keeper.interpret(inp_owed, dec_owed, None)
    assert out_owed.next_speaker == "han" and out_owed.next_reason == "owed_reply"


async def test_extractions_failure_is_non_fatal_and_keeps_decisions_updates() -> None:
    llm = RecordedLLM.from_dir(names=["state_keeper_decisions_ok.json", "wiring_models.json"])
    llm.add([{"status": 400, "json": {"error": {"message": "extract bad"}}}], {"path": "/api/alpha/extractions"})
    ctx, services = _ctx(llm)
    try:
        result = await state_keeper.run(ctx, state_keeper.AgentConfig(), _input())
    finally:
        await services.aclose()
    assert [n.code for n in result.notices] == ["state_keeper_time_failed"]
    assert result.value.state.time == "11:30 Thứ Hai"  # kept old time
    assert result.value.state.location_id == "san_thuong"  # Decisions updates still applied!
    assert "time" not in result.value.changed


async def test_decisions_failure_keeps_structured_state_and_emits_notice() -> None:
    llm = RecordedLLM.from_dir(names=["state_keeper_time_ok.json", "wiring_models.json"])
    llm.add([{"status": 400, "json": {"error": {"message": "decide bad"}}}], {"path": "/api/alpha/decisions"})
    ctx, services = _ctx(llm)
    try:
        result = await state_keeper.run(ctx, state_keeper.AgentConfig(), _input())
    finally:
        await services.aclose()
    assert [n.code for n in result.notices] == ["state_keeper_failed"]
    assert result.value.state.present_ids == ["vy", "han"]
    assert result.value.state.location_id == "can_tin"
    assert result.value.state.time == "12 giờ 30 trưa Thứ Hai"  # Extractions still worked!
