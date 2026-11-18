"""Live smoke test for single chat. Needs the backend running on 127.0.0.1:7880 against the dev DB.

Run from vietrp-studio/backend:  uv run python -I ../scripts/dev/smoke_single_chat.py
It creates a throwaway vault ("Smoke"), a 16-year-old card and a chat, checks the safety layer and error codes, then deletes the chat and card.
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


pp = f"smoke test passphrase {int(time.time())} alpha"
show("create vault", c.post("/api/vault/create", json={"passphrase": pp, "display_name": "Smoke"}))

card = {
    "format": "vietrp-card",
    "spec_version": "1.0",
    "name": "Hân",
    "age": 16,
    "is_fictional": True,
    "tagline": "Học sinh lớp 10, lém lỉnh.",
    "personality": "Lém lỉnh, tò mò.",
    "greetings": ['*Hân ngẩng lên* "Ủa {{user}}, tới rồi hả?"'],
    "tags": ["hoc-duong"],
}
ch = show("create character (age 16)", c.post("/api/characters", json={"data": card, "visibility": "private"}))
cid = ch["character"]["id"]

chat = show("create chat", c.post("/api/chats", json={"mode": "single", "character_id": cid, "greeting_index": 0}))
chat_id = chat.get("id") or chat.get("chat", {}).get("id")
print("chat settings:", json.dumps(chat.get("settings") or chat.get("chat", {}).get("settings"), ensure_ascii=False)[:300])

msgs = show("messages", c.get(f"/api/chats/{chat_id}/messages"), 400)

pv = c.get(f"/api/chats/{chat_id}/prompt-preview", params={"text": "chào Hân"}).json()
layers = [(layer["name"], layer["tokens"]) for layer in pv["layers"]]
print("preview budget", pv["budget"], "total", pv["total_tokens"], "layers", layers)
system_names = [layer["name"] for layer in pv["layers"]]
print("minor_rule present:", "minor_rule" in system_names)

show("turn without key (expect 400 openrouter_key_missing)", c.post(f"/api/chats/{chat_id}/turn", json={"text": "chào Hân"}))

# Adult card with nsfw tag public should pass; minor + nsfw public must be blocked
bad = dict(card, tags=["nsfw"])
show("public minor+nsfw (expect 422 nsfw_minor_public)", c.post("/api/characters", json={"data": bad, "visibility": "public"}))

show("list chats", c.get("/api/chats"), 200)
show("presets", c.get("/api/presets"), 200)
show("cleanup chat", c.delete(f"/api/chats/{chat_id}"))
show("cleanup character", c.delete(f"/api/characters/{cid}"))
