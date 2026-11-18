"""Live smoke test for world chat. Needs the backend running on 127.0.0.1:7880 against the dev DB.

Run from vietrp-studio/backend:  uv run python -I ../scripts/dev/smoke_world_chat.py
Creates a throwaway vault ("Smoke World"), a 16-year-old card, an 18-year-old card, a world, and a world chat;
verifies opening message, `minor_rule` as the LAST system layer in prompt-preview, `PATCH /state` manual tracking,
and 400 `openrouter_key_missing` on `/turn`; then deletes the created resources.
"""

import json
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

import httpx

B = "http://127.0.0.1:7880"
c = httpx.Client(base_url=B, timeout=30)


def show(label: str, r: httpx.Response, keys: int = 300) -> dict:
    body = r.text
    print(f"[{r.status_code}] {label}: {body[:keys]}")
    try:
        return r.json()
    except Exception:
        return {}


pp = f"smoke world passphrase {int(time.time())} beta"
vault_res = c.post("/api/vault/create", json={"passphrase": pp, "display_name": "Smoke World"})
show("create vault", vault_res)
assert vault_res.status_code == 201

han_card = {
    "format": "vietrp-card",
    "spec_version": "1.0",
    "name": "Hân",
    "age": 16,
    "is_fictional": True,
    "tagline": "Học sinh lớp 10, hay ghé căn tin.",
    "personality": "Lém lỉnh, tò mò.",
    "tags": ["hoc-duong"],
}
vy_card = {
    "format": "vietrp-card",
    "spec_version": "1.0",
    "name": "Vy",
    "age": 18,
    "is_fictional": True,
    "tagline": "Sinh viên năm nhất, điềm tĩnh.",
    "personality": "Chín chắn, chu đáo.",
    "tags": ["doi-thuong"],
}

han_res = c.post("/api/characters", json={"data": han_card, "visibility": "private"})
han = show("create minor character (age 16)", han_res)
assert han_res.status_code == 201
han_id = han["character"]["id"]

vy_res = c.post("/api/characters", json={"data": vy_card, "visibility": "private"})
vy = show("create adult character (age 18)", vy_res)
assert vy_res.status_code == 201
vy_id = vy["character"]["id"]

world_data = {
    "format": "vietrp-world",
    "spec_version": "1.0",
    "name": "Sài Gòn Mưa",
    "rules": "Thế giới đời thường ở Sài Gòn.",
    "tags": ["doi-thuong"],
    "locations": [
        {"id": "vn", "parent_id": None, "level": "country", "name": "Việt Nam", "description": ""},
        {"id": "hcm", "parent_id": "vn", "level": "province", "name": "TP.HCM", "description": ""},
        {
            "id": "can_tin",
            "parent_id": "hcm",
            "level": "place",
            "name": "Căn tin",
            "description": "Căn tin vắng người lúc sáng sớm.",
        },
    ],
    "openings": [
        {
            "id": "op1",
            "title": "Sáng mưa",
            "message": "*Mưa rơi ngoài mái hiên.* {{user}} bước vào căn tin.",
            "time": "07:30 Thứ Hai",
            "location_id": "can_tin",
            "present_ids": ["vy", "han"],
            "tension": 1,
            "player_role": "Bạn mới chuyển tới",
        }
    ],
}

world_res = c.post("/api/worlds", json={"data": world_data, "visibility": "private"})
world = show("create world", world_res)
assert world_res.status_code == 201
world_id = world["world"]["id"]

chat_res = c.post(
    "/api/chats",
    json={
        "mode": "world",
        "world_id": world_id,
        "opening_id": "op1",
        "cast_ids": [vy_id, han_id],
    },
)
chat = show("create world chat", chat_res)
assert chat_res.status_code == 201
chat_id = chat["id"]
assert chat["mode"] == "world"
assert len(chat["cast"]) == 2

msgs_res = c.get(f"/api/chats/{chat_id}/messages")
msgs = msgs_res.json()
print(f"[{msgs_res.status_code}] messages:", json.dumps(msgs, ensure_ascii=False)[:300])
assert msgs_res.status_code == 200
assert len(msgs) == 1 and msgs[0]["seq"] == 0 and msgs[0]["speaker"] == "narrator"

# Check prompt-preview: even when adult Vy is the selected speaker, 16yo Hân is present so minor_rule MUST be last system layer.
pv_res = c.get(f"/api/chats/{chat_id}/prompt-preview", params={"text": "chào mọi người", "speaker": "vy"})
assert pv_res.status_code == 200
pv = pv_res.json()
layers = [(layer["name"], layer["tokens"]) for layer in pv["layers"]]
print("preview budget", pv["budget"], "total", pv["total_tokens"], "layers", layers)
system_names = [layer["name"] for layer in pv["layers"] if layer["name"] not in ("history", "prefill")]
print("system layers:", system_names)
assert "minor_rule" in system_names
assert system_names[-1] == "minor_rule", f"expected minor_rule last, got {system_names}"

patch_res = c.patch(
    f"/api/chats/{chat_id}/state",
    json={
        "location_id": "hcm",
        "time": "08:00 Thứ Hai",
        "tension": 2,
        "scene": {"env": {"weather": "tạnh mưa"}, "chars": {}, "items": ["chiếc ô"]},
    },
)
patched = show("patch world state", patch_res)
assert patch_res.status_code == 200
assert patched["state"]["location_id"] == "hcm"
assert patched["state"]["tension"] == 2
assert set(["location_id", "time", "tension", "scene"]) <= set(patched["state"]["manual"])

turn_res = c.post(f"/api/chats/{chat_id}/turn", json={"text": "chào mọi người"})
turn_err = show("turn without key (expect 400 openrouter_key_missing)", turn_res)
assert turn_res.status_code == 400 and turn_err["error"]["code"] == "openrouter_key_missing"

show("cleanup chat", c.delete(f"/api/chats/{chat_id}"))
show("cleanup world", c.delete(f"/api/worlds/{world_id}"))
show("cleanup han", c.delete(f"/api/characters/{han_id}"))
show("cleanup vy", c.delete(f"/api/characters/{vy_id}"))
print("WORLD CHAT SMOKE TEST PASSED")
