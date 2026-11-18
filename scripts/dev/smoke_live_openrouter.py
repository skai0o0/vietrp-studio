"""Live OpenRouter E2E smoke test for single chat (P2) and world chat (P3).

Reads `OPENROUTER_API_KEY` in-memory from workspace `.env` (never prints or logs it),
creates a throwaway vault on `http://127.0.0.1:7880`, runs one live Single Chat turn
and one live World Chat turn against OpenRouter, checks usage and SSE flow, then cleans up.

Run from vietrp-studio/backend:  uv run python -I ../scripts/dev/smoke_live_openrouter.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

BASE_URL = "http://127.0.0.1:7880"
ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


def _load_openrouter_key() -> str:
    if ROOT_ENV.is_file():
        for raw in ROOT_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "OPENROUTER_API_KEY" and v.strip():
                return v.strip().strip("'\"")
    env_val = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_val:
        return env_val
    raise RuntimeError("OPENROUTER_API_KEY not found in workspace .env or environment")


def _stream_sse(client: httpx.Client, path: str, body: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with client.stream("POST", path, json=body or {}, timeout=120) as resp:
        assert resp.status_code == 200, f"SSE {path} failed {resp.status_code}: {resp.read().decode(errors='replace')}"
        cur_data: list[str] = []
        for raw_line in resp.iter_lines():
            if raw_line == "":
                if cur_data:
                    payload = "\n".join(cur_data)
                    cur_data.clear()
                    events.append(json.loads(payload))
                continue
            if raw_line.startswith("data:"):
                cur_data.append(raw_line[5:].lstrip())
        if cur_data:
            events.append(json.loads("\n".join(cur_data)))
    return events


def _stream_turn(client: httpx.Client, chat_id: str, text: str) -> list[dict[str, Any]]:
    return _stream_sse(client, f"/api/chats/{chat_id}/turn", {"text": text})


def main() -> None:
    api_key = _load_openrouter_key()
    print(f"OPENROUTER_API_KEY loaded in memory: {bool(api_key)}")

    client = httpx.Client(base_url=BASE_URL, timeout=60)
    created_chats: list[str] = []
    created_worlds: list[str] = []
    created_chars: list[str] = []
    created_personas: list[str] = []

    try:
        pp = f"smoke live openrouter {int(time.time())} zeta"
        v_res = client.post("/api/vault/create", json={"passphrase": pp, "display_name": "Smoke Live"})
        assert v_res.status_code == 201, v_res.text
        print("[201] created throwaway vault")

        sec_res = client.put("/api/secrets/OPENROUTER_API_KEY", json={"value": api_key})
        assert sec_res.status_code == 200, sec_res.text
        print("[200] stored OPENROUTER_API_KEY secret (hint:", sec_res.json()["secret"]["hint"], ")")

        models_res = client.get("/api/models")
        assert models_res.status_code == 200, models_res.text
        models = models_res.json()
        assert len(models) > 0
        print(f"[200] GET /api/models returned {len(models)} models")

        persona_res = client.post(
            "/api/personas",
            json={
                "data": {
                    "format": "vietrp-persona",
                    "spec_version": "1.0",
                    "name": "Minh",
                    "age": 21,
                    "gender": "nam",
                    "pronouns": "tớ - cậu",
                    "personality": "Thoải mái, hay quan tâm bạn bè.",
                }
            },
        )
        assert persona_res.status_code == 201, persona_res.text
        persona_id = persona_res.json()["persona"]["id"]
        created_personas.append(persona_id)

        vy_res = client.post(
            "/api/characters",
            json={
                "visibility": "private",
                "data": {
                    "format": "vietrp-card",
                    "spec_version": "1.0",
                    "name": "Trần Hạ Vy",
                    "age": 20,
                    "is_fictional": True,
                    "tagline": "Lớp phó năng động, hay cười nhưng rất để tâm việc lớp.",
                    "personality": "Thẳng thắn, nói nhanh, đôi lúc hơi nóng nảy nhưng tốt bụng.",
                    "speech": {"style": "nói ngắn gọn, xưng cậu - tớ"},
                    "goals": "Chuẩn bị xong tài liệu cho buổi sinh hoạt tuần này.",
                    "greetings": ['*Vy ngẩng đầu khỏi xấp giấy, vẫy tay* "Minh ơi, qua bàn này ngồi đi!"'],
                    "tags": ["doi-thuong"],
                },
            },
        )
        assert vy_res.status_code == 201, vy_res.text
        vy_id = vy_res.json()["character"]["id"]
        created_chars.append(vy_id)

        han_res = client.post(
            "/api/characters",
            json={
                "visibility": "private",
                "data": {
                    "format": "vietrp-card",
                    "spec_version": "1.0",
                    "name": "Nguyễn Gia Hân",
                    "age": 21,
                    "is_fictional": True,
                    "tagline": "Thư viện trưởng trầm tĩnh, thích trà nóng.",
                    "personality": "Điềm đạm, ít nói nhưng quan sát rất kỹ.",
                    "speech": {"style": "nhẹ nhàng, xưng mình - cậu"},
                    "goals": "Đọc xong cuốn sách trước giờ đóng cửa.",
                    "tags": ["doi-thuong"],
                },
            },
        )
        assert han_res.status_code == 201, han_res.text
        han_id = han_res.json()["character"]["id"]
        created_chars.append(han_id)

        # --- 1. Live Single Chat ---
        sc_res = client.post(
            "/api/chats",
            json={"mode": "single", "character_id": vy_id, "persona_id": persona_id, "greeting_index": 0},
        )
        assert sc_res.status_code == 201, sc_res.text
        sc_id = sc_res.json()["id"]
        created_chats.append(sc_id)

        sc_events = _stream_turn(client, sc_id, "Chào Vy, hôm nay cậu còn nhiều giấy tờ phải soạn không?")
        sc_types = [e["type"] for e in sc_events]
        sc_notices = [(e.get("code"), e.get("agent"), e.get("detail")) for e in sc_events if e["type"] == "notice"]
        sc_usage = [e for e in sc_events if e["type"] == "usage"]
        print("Single Chat SSE types:", sc_types)
        print("Single Chat notices:", sc_notices)
        print("Single Chat usage events:", sc_usage)
        assert "done" in sc_types and "error" not in sc_types, f"Single chat failed: {sc_events}"
        assert any(e["type"] == "speaker_end" for e in sc_events)

        sc_msgs = client.get(f"/api/chats/{sc_id}/messages").json()
        assert len(sc_msgs) >= 3, f"expected greeting + user + ai, got {len(sc_msgs)}"
        print("Single Chat AI reply snippet:", sc_msgs[-1]["variants"][0]["content"][:160])

        sc_usage_rows = client.get(f"/api/usage?chat_id={sc_id}").json()
        print("Single Chat usage_log count:", len(sc_usage_rows))
        assert len(sc_usage_rows) >= 1

        # --- 2. Live World Chat ---
        w_res = client.post(
            "/api/worlds",
            json={
                "visibility": "private",
                "data": {
                    "format": "vietrp-world",
                    "spec_version": "1.0",
                    "name": "Khuôn viên Đại học",
                    "rules": "Thế giới đời thường ở khuôn viên đại học Việt Nam.",
                    "tags": ["doi-thuong"],
                    "locations": [
                        {"id": "khuon_vien", "parent_id": None, "level": "area", "name": "Khuôn viên", "description": ""},
                        {
                            "id": "can_tin",
                            "parent_id": "khuon_vien",
                            "level": "place",
                            "name": "Căn tin",
                            "description": "Căn tin thoáng mát, có dãy bàn gỗ gần cửa sổ.",
                        },
                        {
                            "id": "thu_vien",
                            "parent_id": "khuon_vien",
                            "level": "place",
                            "name": "Thư viện",
                            "description": "Thư viện yên tĩnh ở tầng hai.",
                        },
                    ],
                    "openings": [
                        {
                            "id": "op1",
                            "title": "Giờ nghỉ trưa",
                            "message": "*Nắng trưa hắt qua khung cửa sổ căn tin.* Vy và Hân đang ngồi đợi {{user}}.",
                            "time": "12:15 Thứ Tư",
                            "location_id": "can_tin",
                            "present_ids": ["vy", "han"],
                            "tension": 0,
                            "player_role": "Bạn cùng nhóm học tập",
                        }
                    ],
                },
            },
        )
        assert w_res.status_code == 201, w_res.text
        world_id = w_res.json()["world"]["id"]
        created_worlds.append(world_id)

        wc_res = client.post(
            "/api/chats",
            json={
                "mode": "world",
                "world_id": world_id,
                "opening_id": "op1",
                "cast_ids": [vy_id, han_id],
                "persona_id": persona_id,
            },
        )
        assert wc_res.status_code == 201, wc_res.text
        wc_id = wc_res.json()["id"]
        created_chats.append(wc_id)

        wc_events = _stream_turn(client, wc_id, "Mình mua hai ly trà đào mang tới cho Vy với Hân đây.")
        wc_types = [e["type"] for e in wc_events]
        wc_notices = [(e.get("code"), e.get("agent"), e.get("detail")) for e in wc_events if e["type"] == "notice"]
        wc_state = next((e for e in wc_events if e["type"] == "state"), None)
        print("World Chat SSE types:", wc_types)
        print("World Chat notices:", wc_notices)
        print("World Chat state event:", wc_state)
        assert "done" in wc_types and "error" not in wc_types, f"World chat failed: {wc_events}"
        assert any(e["type"] == "speaker_end" for e in wc_events)

        wc_msgs = client.get(f"/api/chats/{wc_id}/messages").json()
        assert len(wc_msgs) >= 3
        for m in wc_msgs:
            assert "<scene" not in m["variants"][0]["content"]
        print("World Chat last AI reply snippet:", wc_msgs[-1]["variants"][0]["content"][:160])

        wc_usage_rows = client.get(f"/api/usage?chat_id={wc_id}").json()
        print("World Chat usage_log count:", len(wc_usage_rows))
        assert len(wc_usage_rows) >= 1

        # --- 3. P4 + P5 Live Checks (Summarize, Commands, Continue, Regenerate, Swipe, Fork, Undo) ---
        cont_events = _stream_sse(client, f"/api/chats/{sc_id}/continue", {})
        assert "done" in [e["type"] for e in cont_events] and "error" not in [e["type"] for e in cont_events]
        sc_msgs = client.get(f"/api/chats/{sc_id}/messages").json()
        target_msg_id = sc_msgs[-1]["id"]

        regen_events = _stream_sse(client, f"/api/messages/{target_msg_id}/regenerate", {})
        assert "done" in [e["type"] for e in regen_events] and "error" not in [e["type"] for e in regen_events]
        sc_msgs = client.get(f"/api/chats/{sc_id}/messages").json()
        assert len(sc_msgs[-1]["variants"]) == 2
        swiped = client.put(f"/api/messages/{target_msg_id}/active-variant", json={"variant_idx": 0})
        assert swiped.status_code == 200 and swiped.json()["active_variant"] == 0

        sum_res = client.post(f"/api/chats/{sc_id}/summarize")
        assert sum_res.status_code == 200, sum_res.text
        sum_state = sum_res.json()["state"]
        assert sum_state.get("summary") and int(sum_state.get("summary_upto", 0)) >= 1
        print("[200] P4 live Archivist summarize snippet:", sum_state["summary"][:120])

        fork_res = client.post(f"/api/chats/{sc_id}/fork", json={"upto_seq": 1, "title": "Smoke Fork"})
        assert fork_res.status_code == 201, fork_res.text
        fork_id = fork_res.json()["id"]
        created_chats.append(fork_id)
        assert fork_res.json()["parent_chat_id"] == sc_id and fork_res.json()["forked_at_seq"] == 1

        undo_res = client.post(f"/api/chats/{sc_id}/undo")
        assert undo_res.status_code == 200, undo_res.text
        assert undo_res.json()["removed_count"] >= 1

        for cmd_text, expected_notice in (
            ("/time 18:30 Thứ Tư", "time_updated"),
            ("/move thu_vien", "location_moved"),
            ("/addnpc Bác Bảo Vệ (52) - Trực cổng thư viện", "npc_added"),
            ("/listnpc", "npc_listed"),
            ("/clearnpc", "npc_cleared"),
        ):
            cmd_events = _stream_turn(client, wc_id, cmd_text)
            assert any(e["type"] == "notice" and e["code"] == expected_notice for e in cmd_events), (cmd_text, cmd_events)

        # --- 4. P6 Live Creator + Card Judge ---
        pools_res = client.get("/api/creator/pools")
        assert pools_res.status_code == 200 and "character" in pools_res.json() and "world" in pools_res.json()

        judge_ch = client.post(f"/api/characters/{vy_id}/judge")
        assert judge_ch.status_code == 200, judge_ch.text
        ch_score = judge_ch.json()["character"]["judge_score"]
        assert ch_score and len(ch_score["criteria"]) == 6
        print(f"[200] P6 Card Judge character score={ch_score['score']:.2f} passed={ch_score['passed']}")

        judge_w = client.post(f"/api/worlds/{world_id}/judge")
        assert judge_w.status_code == 200, judge_w.text
        w_score = judge_w.json()["world"]["judge_score"]
        assert w_score and len(w_score["criteria"]) == 6
        print(f"[200] P6 Card Judge world score={w_score['score']:.2f} passed={w_score['passed']}")

        sess_res = client.post(
            "/api/creator/sessions",
            json={
                "mode": "slots",
                "target_type": "character",
                "seed": {
                    "name": "Lâm Hải Đăng",
                    "age": 24,
                    "gender": "Nam",
                    "occupation": "Kiến trúc sư phục chế nhà cổ",
                    "personality_archetype": "Ngoài lạnh trong nóng: ít nói nhưng tinh tế.",
                    "speech_style": "Chậm rãi, xưng tôi - cậu.",
                },
            },
        )
        assert sess_res.status_code == 201, sess_res.text
        sess_id = sess_res.json()["id"]
        gen_events = _stream_sse(client, f"/api/creator/sessions/{sess_id}/generate", {"skip_raw": False})
        gen_types = [e["type"] for e in gen_events]
        print("P6 Creator generate SSE types:", gen_types)
        assert "raw" in gen_types and "formatted" in gen_types and "validated" in gen_types and "done" in gen_types
        assert "error" not in gen_types, f"Creator generate failed: {gen_events}"

        done_ev = next(e for e in gen_events if e["type"] == "done")
        gen_data = dict(done_ev["session"]["result"]["data"])
        if gen_data.get("age") is None:
            gen_data["age"] = 24
        save_res = client.post(f"/api/creator/sessions/{sess_id}/save", json={"visibility": "private", "data": gen_data})
        assert save_res.status_code == 201, save_res.text
        saved_char_id = save_res.json()["item_id"]
        created_chars.append(saved_char_id)
        print("[201] P6 Creator saved character:", save_res.json()["character"]["name"])

        # --- 5. P7 Static SPA check (when frontend/dist exists) ---
        root_res = client.get("/")
        if root_res.status_code == 200:
            assert "text/html" in root_res.headers.get("content-type", "")
            print("[200] P7 Built SPA index.html served from FastAPI root /")

        print("LIVE OPENROUTER E2E SMOKE TEST PASSED (P2-P7)")
    finally:
        for cid in created_chats:
            client.delete(f"/api/chats/{cid}")
        for wid in created_worlds:
            client.delete(f"/api/worlds/{wid}")
        for chid in created_chars:
            client.delete(f"/api/characters/{chid}")
        for pid in created_personas:
            client.delete(f"/api/personas/{pid}")


if __name__ == "__main__":
    main()
