"""Unit tests for Creator agent (interview, draft_raw, format_json, repair, and error paths)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from app.agents import creator
from app.agents.base import AgentContext
from app.llm.client import LLMError
from app.llm.fake import RecordedLLM
from tests.conftest import make_settings
from tests.llm.test_wiring import make_gateway


def _completion(content: str) -> dict[str, object]:
    return {
        "status": 200,
        "json": {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 110, "completion_tokens": 60, "cost": 0.0002},
        },
    }


def _stream(*parts: str) -> dict[str, object]:
    chunks: list[dict[str, object]] = [{"id": "c1", "choices": [{"delta": {"role": "assistant", "content": ""}}]}]
    chunks += [{"id": "c1", "choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in parts]
    chunks.append({"id": "c1", "choices": [{"delta": {}, "finish_reason": "stop"}]})
    chunks.append({"id": "c1", "choices": [], "usage": {"prompt_tokens": 90, "completion_tokens": 20, "cost": 0.0001}})
    return {"status": 200, "sse": chunks}


async def test_creator_interview_reply_and_stream() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add(
        [_completion("Nghe thú vị đấy! Nhân vật này bao nhiêu tuổi và đang làm nghề gì?")],
        {"path": "/api/v1/chat/completions", "stream": False},
    )
    llm.add(
        [_stream("Tôi đã nắm ý chính: ", "cô ấy 24 tuổi, làm thợ sửa đồng hồ.")],
        {"path": "/api/v1/chat/completions", "stream": True},
    )
    gateway, services, recorder, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    cfg = creator.AgentConfig()
    try:
        reply = await creator.interview_reply(
            ctx,
            cfg,
            target_type="character",
            seed={"format_trope": "Thợ sửa đồng hồ"},
            messages=[{"role": "user", "content": "Tạo cô gái lạnh lùng {{ 7 * 7 }}"}],
            user_message="Cô ấy ít nói và hay thức khuya.",
        )
        deltas: list[str] = []
        done: creator.CreatorDone | None = None
        async for ev in creator.interview_stream(
            ctx,
            cfg,
            target_type="character",
            seed={},
            messages=[],
            user_message="Cô ấy 24 tuổi.",
        ):
            if isinstance(ev, creator.CreatorDelta):
                deltas.append(ev.text)
            else:
                done = ev
    finally:
        await services.aclose()

    assert "bao nhiêu tuổi" in reply.value
    assert "".join(deltas) == "Tôi đã nắm ý chính: cô ấy 24 tuổi, làm thợ sửa đồng hồ."
    assert done is not None and done.text == "".join(deltas)
    assert [c[2] for c in recorder.calls] == ["creator", "creator"]

    first_req = json.loads(llm.requests[0].content)
    assert first_req["messages"][0]["role"] == "system"
    assert first_req["messages"][1]["role"] == "system"  # creator minor-safety rule
    assert "{{ 7 * 7 }}" in first_req["messages"][2]["content"]


async def test_creator_draft_raw_for_character_and_world() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([_completion("[TÊN]\nLan Anh\n[TUỔI]\n24")], {"contains": "vietrp-card"})
    llm.add([_completion("[TÊN THỰC TẠI]\nPhố Mưa")], {"contains": "vietrp-world"})
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        card_raw = await creator.draft_raw(
            ctx,
            creator.AgentConfig(),
            target_type="character",
            seed={"occupation": "Thợ sửa đồng hồ"},
            messages=[{"role": "user", "content": "Tên Lan Anh, 24 tuổi."}],
        )
        world_raw = await creator.draft_raw(
            ctx,
            creator.AgentConfig(),
            target_type="world",
            seed={"tone": "Trầm lắng"},
            messages=[{"role": "user", "content": "Bối cảnh Phố Mưa."}],
        )
    finally:
        await services.aclose()

    assert "Lan Anh" in card_raw.value
    assert "Phố Mưa" in world_raw.value


async def test_creator_format_json_repairs_card_and_validates() -> None:
    # Missing format, spec_version, is_fictional; string age; fenced JSON; raw secret id with accents.
    fenced = (
        "Dưới đây là JSON:\n```json\n"
        + json.dumps(
            {
                "name": "Lan Anh",
                "age": "24 tuổi",
                "tagline": "Thợ sửa đồng hồ cũ.",
                "personality": "Điềm tĩnh, kín tiếng.",
                "goals": "Tìm chiếc đồng hồ mất tích.",
                "secrets": [{"id": "Bí Mật Lớn!", "content": "Giữ chìa khóa tầng hầm.", "reveal_when": "Tin tưởng"}],
                "tags": ["Slice", "Đời Thường"],
                "bogus_extra": "ignored",
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    missing_age_json = json.dumps({"name": "Khách Lạ", "age": "không rõ", "personality": "Bí ẩn."})

    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([_completion(fenced)], {"contains": "Lan Anh"})
    llm.add([_completion(missing_age_json)], {"contains": "Khách Lạ"})
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        card_data, warnings, usage = await creator.format_json(
            ctx, creator.AgentConfig(), target_type="character", raw_draft="Lan Anh 24 tuổi", seed={}
        )
        unknown_age_data, age_warnings, _ = await creator.format_json(
            ctx, creator.AgentConfig(), target_type="character", raw_draft="Khách Lạ chưa rõ tuổi", seed={}
        )
    finally:
        await services.aclose()

    assert card_data["format"] == "vietrp-card"
    assert card_data["spec_version"] == "1.0"
    assert card_data["is_fictional"] is True
    assert card_data["age"] == 24
    assert card_data["secrets"][0]["id"] == "bi_mat_lon"
    assert card_data["tags"] == ["slice", "đời thường"]
    assert "bogus_extra" not in card_data
    assert warnings == []
    assert usage.prompt_tokens == 110

    assert unknown_age_data["age"] is None
    assert [w.code for w in age_warnings] == ["age_missing"]


async def test_creator_format_json_repairs_world_tree_and_openings() -> None:
    payload = json.dumps(
        {
            "name": "Thành Phố Mưa",
            "rules": "Thế giới hiện đại không phép thuật.",
            "locations": [
                {"id": "Quận 1", "parent_id": None, "level": "district", "name": "Quận 1"},
                # Same level as parent ("district" under "district"): repair bumps child to "area".
                {"id": "Khu Phố Cổ", "parent_id": "Quận 1", "level": "district", "name": "Khu Phố Cổ"},
            ],
            "openings": [
                {
                    "id": "Cảnh Một!",
                    "title": "Quán khuya",
                    "location_id": "Khu Phố Cổ",
                    "message": "Mưa rơi lách tách ngoài hiên.",
                    "tension": 9,
                }
            ],
            "tags": ["Modern"],
        },
        ensure_ascii=False,
    )
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([_completion(payload)], {"path": "/api/v1/chat/completions"})
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        world_data, warnings, _ = await creator.format_json(
            ctx, creator.AgentConfig(), target_type="world", raw_draft="Thành phố mưa", seed={}
        )
    finally:
        await services.aclose()

    assert world_data["format"] == "vietrp-world"
    assert world_data["locations"][0]["id"] == "quan_1"
    assert world_data["locations"][1]["id"] == "khu_pho_co"
    assert world_data["locations"][1]["parent_id"] == "quan_1"
    assert world_data["locations"][1]["level"] == "area"
    assert world_data["openings"][0]["id"] == "canh_mot"
    assert world_data["openings"][0]["location_id"] == "khu_pho_co"
    assert world_data["openings"][0]["tension"] == 4
    assert warnings == []


async def test_creator_format_json_errors_on_invalid_json_or_missing_name() -> None:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    llm.add([_completion("Đây không phải JSON hợp lệ chút nào.")], {"contains": "bad_syntax"})
    llm.add([_completion('{"name": "", "age": 20}')], {"contains": "empty_name"})
    gateway, services, _, _ = make_gateway(llm)
    ctx = AgentContext(vault_id=gateway.vault_id, chat_id=None, llm=gateway, settings=make_settings())
    try:
        with pytest.raises(LLMError) as exc_info:
            await creator.format_json(
                ctx, creator.AgentConfig(), target_type="character", raw_draft="bad_syntax", seed={}
            )
        assert exc_info.value.code == "llm_bad_response"

        with pytest.raises(ValidationError):
            await creator.format_json(
                ctx, creator.AgentConfig(), target_type="character", raw_draft="empty_name", seed={}
            )
    finally:
        await services.aclose()
