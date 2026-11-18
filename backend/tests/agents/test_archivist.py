"""Unit tests for the Archivist agent and `parse_archivist`."""

from __future__ import annotations

import json
import unicodedata

from app.agents import archivist
from app.agents.base import AgentContext
from app.core.config import MAX_EVENTS
from app.llm.fake import RecordedLLM
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def test_parse_archivist_valid_headers_slugs_dedup_and_events_added() -> None:
    raw = """
    TÓM TẮT:
    - Nam và Vy gặp nhau ở căn tin buổi sáng.
    - Vy đưa cho Nam chiếc chìa khóa phòng thí nghiệm.

    SỰ KIỆN ĐÁNG NHỚ:
    - Vy đưa chìa khóa cho Nam | Vy giao chìa khóa phòng thí nghiệm cho Nam giữ tới chiều.
    * Vy đưa chìa khóa cho Nam | Bản trùng tiêu đề phải bị bỏ qua.
    • Hân biết bí mật của Đạt : Hân đọc được nhật ký của Đạt ở thư viện.
    - (chưa có)
    """
    summary, events, added = archivist.parse_archivist(raw)
    assert summary == "- Nam và Vy gặp nhau ở căn tin buổi sáng.\n- Vy đưa cho Nam chiếc chìa khóa phòng thí nghiệm."
    assert len(events) == 2
    assert added == 2
    assert events[0] == archivist.MemorableEvent(
        id="sk_vy_dua_chia_khoa_cho_nam",
        title="Vy đưa chìa khóa cho Nam",
        content="Vy giao chìa khóa phòng thí nghiệm cho Nam giữ tới chiều.",
    )
    assert events[1] == archivist.MemorableEvent(
        id="sk_han_biet_bi_mat_cua_dat",
        title="Hân biết bí mật của Đạt",
        content="Hân đọc được nhật ký của Đạt ở thư viện.",
    )

    # Re-parsing identical event + one updated event + one new event counts only updated/new.
    raw_next = """
    **TÓM TẮT:**
    - Cả nhóm lên sân thượng sau giờ học.

    ### SỰ KIỆN ĐÁNG NHỚ:
    - Vy đưa chìa khóa cho Nam | Vy giao chìa khóa phòng thí nghiệm cho Nam giữ tới chiều.
    - Hân biết bí mật của Đạt | Hân đã trả lại nhật ký và hứa giữ bí mật cho Đạt.
    - Tuấn hẹn Nam đấu bóng | Tuấn rủ Nam ra sân lúc 5 giờ chiều.
    """
    _, events_next, added_next = archivist.parse_archivist(raw_next, previous_events=events)
    assert len(events_next) == 3
    assert added_next == 2  # 1 updated (Hân) + 1 new (Tuấn); unchanged Vy counts 0


def test_parse_archivist_missing_headers_falls_back_to_summary_only() -> None:
    raw = "Nam và Vy nói chuyện về kỳ thi.\nHọ hẹn nhau ôn bài tối nay."
    summary, events, added = archivist.parse_archivist(raw)
    assert summary == raw
    assert events == []
    assert added == 0


def test_parse_archivist_normalizes_nfd_and_caps_at_max_events() -> None:
    lines = ["TÓM TẮT:", "- Diễn biến chính.", "SỰ KIỆN ĐÁNG NHỚ:"]
    for idx in range(MAX_EVENTS + 5):
        lines.append(f"- Đạt ghi sự kiện số {idx} | Chi tiết sự kiện thứ {idx}.")
    nfd_payload = unicodedata.normalize("NFD", "\n".join(lines))

    summary, events, added = archivist.parse_archivist(nfd_payload)
    assert unicodedata.is_normalized("NFC", summary)
    assert summary == "- Diễn biến chính."
    assert len(events) == MAX_EVENTS
    assert added == MAX_EVENTS
    assert all(ev.id.startswith("sk_") and unicodedata.is_normalized("NFC", ev.title) for ev in events)
    assert all(unicodedata.is_normalized("NFC", ev.content) for ev in events)
    assert events[0].id == "sk_dat_ghi_su_kien_so_0"


async def test_archivist_run_marks_priority_disables_reasoning_and_escapes_user_jinja() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add(
        [
            {
                "status": 200,
                "json": {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": (
                                    "TÓM TẮT:\n- Nam và Vy trao đổi mật mã {{ 7 * 7 }}.\n\n"
                                    "SỰ KIỆN ĐÁNG NHỚ:\n"
                                    "- Vy giao mật mã cho Nam | Vy nói nhỏ mật mã cho Nam trước khi rời đi."
                                ),
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 120, "completion_tokens": 45, "cost": 0.0002},
                },
            }
        ],
        {"path": "/api/v1/chat/completions", "stream": False},
        name="archivist",
    )
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=gateway.chat_id, llm=gateway, settings=make_settings())
    try:
        empty_res = await archivist.run(ctx, archivist.AgentConfig(), archivist.ArchivistInput(messages=[]))
        assert empty_res.value.upto_seq == 0 and empty_res.value.events_added == 0
        assert llm.requests == []

        inp = archivist.ArchivistInput(
            messages=[
                archivist.ArchivistMessage(seq=2, speaker_name="Nam", content="Chào {{ 7 * 7 }}", priority=0),
                archivist.ArchivistMessage(seq=3, speaker_name="Vy", content="Nghe kỹ nhé {% if x %}", priority=2),
                archivist.ArchivistMessage(seq=4, speaker_name="Vy", content="Đừng quên.", priority=1),
            ],
            previous_summary="- Hai người gặp nhau ở sân trường.",
            previous_events=[
                archivist.MemorableEvent(id="sk_nam_gap_vy", title="Nam gặp Vy", content="Nam gặp Vy ở sân trường.")
            ],
        )
        res = await archivist.run(ctx, archivist.AgentConfig(), inp)
    finally:
        await services.aclose()

    assert res.value.upto_seq == 5
    assert res.value.events_added == 1
    assert res.value.events[0].id == "sk_vy_giao_mat_ma_cho_nam"
    assert len(res.usage) == 1 and res.usage[0].prompt_tokens == 120

    assert len(llm.requests) == 1
    body = json.loads(llm.requests[0].content)
    assert body["reasoning"] == {"enabled": False}
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 1400
    user_prompt = body["messages"][1]["content"]
    assert "[QUAN TRỌNG] Vy: Nghe kỹ nhé {% if x %}" in user_prompt
    assert "[ĐÁNG CHÚ Ý] Vy: Đừng quên." in user_prompt
    assert "Nam: Chào {{ 7 * 7 }}" in user_prompt
    assert "[QUAN TRỌNG] Nam:" not in user_prompt
