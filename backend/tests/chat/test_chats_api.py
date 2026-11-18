"""Chat CRUD, messages, bonds, presets, utility routes, vault isolation and the safety layer."""

from __future__ import annotations

import json
from typing import Any

from tests.chat.conftest import (
    ChatEnv,
    make_character,
    make_chat,
    make_persona,
    run_turn,
    script_llm,
    sse_stream,
)


async def test_chat_crud_messages_and_greeting(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id, greeting_index=1, title="Chat thử")
    assert chat["mode"] == "single" and chat["title"] == "Chat thử" and chat["messages_count"] == 1
    assert (
        chat["state"] == {"bonds": {}, "summary": "", "summary_upto": 0, "events": []}
        and chat["settings"]["director"]["enabled"] is True
    )

    rows = (await env.a.get(f"/api/chats/{chat['id']}/messages")).json()
    assert len(rows) == 1 and rows[0]["seq"] == 0 and rows[0]["speaker"] == character_id
    assert rows[0]["variants"][0]["content"] == "Lời mở đầu thứ hai"
    assert (await env.a.get(f"/api/chats/{chat['id']}/messages?before=0")).json() == []

    listing = (await env.a.get("/api/chats")).json()
    assert [c["id"] for c in listing] == [chat["id"]] and listing[0]["character_name"] == "Mai"

    patched = await env.a.patch(
        f"/api/chats/{chat['id']}",
        json={"title": "Đổi tên", "settings": {"director": {"stream_mode": "hold_until_approved"}, "nsfw": True}},
    )
    assert patched.status_code == 200
    assert patched.json()["settings"]["director"]["stream_mode"] == "hold_until_approved"
    assert patched.json()["title"] == "Đổi tên"

    assert (await env.a.delete(f"/api/chats/{chat['id']}")).status_code == 204
    gone = await env.a.get(f"/api/chats/{chat['id']}")
    assert gone.status_code == 404 and gone.json()["error"]["code"] == "chat_not_found"


async def test_message_pagination(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(env.llm, character_id, writer=[sse_stream("Một."), sse_stream("Hai.")])
    await run_turn(env.a, chat["id"], "A")
    await run_turn(env.a, chat["id"], "B")  # seq 0..4
    newest = (await env.a.get(f"/api/chats/{chat['id']}/messages?limit=2")).json()
    assert [m["seq"] for m in newest] == [3, 4]
    older = (await env.a.get(f"/api/chats/{chat['id']}/messages?limit=2&before=3")).json()
    assert [m["seq"] for m in older] == [1, 2]


async def test_create_validation(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    missing_world = await env.a.post("/api/chats", json={"mode": "world", "character_id": character_id})
    assert missing_world.status_code == 422 and missing_world.json()["error"]["code"] == "validation_error"
    invalid_mode = await env.a.post("/api/chats", json={"mode": "x", "character_id": character_id})
    assert invalid_mode.status_code == 422 and invalid_mode.json()["error"]["code"] == "validation_error"
    bad_greeting = await env.a.post("/api/chats", json={"character_id": character_id, "greeting_index": 9})
    assert bad_greeting.status_code == 422 and bad_greeting.json()["error"]["code"] == "greeting_index_invalid"
    unknown = await env.a.post("/api/chats", json={"character_id": "00000000-0000-0000-0000-000000000000"})
    assert unknown.status_code == 404


async def test_card_without_age_cannot_start_a_chat(env: ChatEnv) -> None:
    raw = json.dumps({"name": "Bare", "description": "Một nhân vật", "first_mes": "Xin chào"}).encode()
    imported = await env.a.post("/api/import", files={"file": ("bare.json", raw, "application/octet-stream")})
    assert imported.status_code == 201, imported.text
    response = await env.a.post("/api/chats", json={"character_id": imported.json()["character"]["id"]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "age_required"


async def test_minor_rule_is_the_last_system_layer_in_the_preview(env: ChatEnv) -> None:
    adult = await make_chat(env.a, await make_character(env.a))
    minor = await make_chat(env.a, await make_character(env.a, name="Bé Na", age=12), settings={"nsfw": True})
    plain = (await env.a.get(f"/api/chats/{adult['id']}/prompt-preview?text=Chào")).json()
    assert "minor_rule" not in [layer["name"] for layer in plain["layers"]]
    assert plain["budget"] > 0 and plain["total_tokens"] > 0

    # Also under a `/cmd` instruction and with NSFW switched on.
    for text in ("Chào", "/cmd [hãy táo bạo hơn] Chào"):
        preview = (await env.a.get(f"/api/chats/{minor['id']}/prompt-preview", params={"text": text})).json()
        names = [layer["name"] for layer in preview["layers"]]
        assert "minor_rule" in names and "nsfw" in names
        system = [n for n in names if n not in ("history", "prefill")]
        assert system[-1] == "minor_rule"
        assert all({"name", "tokens", "text"} <= set(layer) for layer in preview["layers"])


async def test_bonds_patch_marks_edited_fields_manual(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    script_llm(env.llm, character_id, writer=[sse_stream("Dạ.")])
    await run_turn(env.a, chat["id"], "Chào")
    pair = f"{character_id}:user"
    bonds = (await env.a.get(f"/api/chats/{chat['id']}")).json()["state"]["bonds"]
    edited = json.loads(json.dumps(bonds[pair]))
    edited["fields"]["nickname"] = "Bé Mai"
    response = await env.a.patch(f"/api/chats/{chat['id']}/state", json={"bonds": {pair: edited}})
    assert response.status_code == 200, response.text
    record = response.json()["state"]["bonds"][pair]
    assert record["fields"]["nickname"] == "Bé Mai" and record["manual"] == ["nickname"]
    assert record["changes"] == bonds[pair]["changes"]
    bad = await env.a.patch(f"/api/chats/{chat['id']}/state", json={"bonds": {pair: {"nope": 1}}})
    assert bad.status_code == 422


async def test_vault_isolation_on_every_route(env: ChatEnv) -> None:
    character_id = await make_character(env.a)
    chat = await make_chat(env.a, character_id)
    cid = chat["id"]
    checks: list[tuple[str, str, dict[str, Any]]] = [
        ("GET", f"/api/chats/{cid}", {}),
        ("PATCH", f"/api/chats/{cid}", {"json": {"title": "x"}}),
        ("DELETE", f"/api/chats/{cid}", {}),
        ("GET", f"/api/chats/{cid}/messages", {}),
        ("GET", f"/api/chats/{cid}/prompt-preview", {}),
        ("PATCH", f"/api/chats/{cid}/state", {"json": {"bonds": {}}}),
        ("POST", f"/api/chats/{cid}/turn", {"json": {"text": "hi"}}),
        ("POST", f"/api/chats/{cid}/stop", {}),
        ("GET", f"/api/usage?chat_id={cid}", {}),
    ]
    for method, path, kwargs in checks:
        response = await env.b.request(method, path, **kwargs)
        assert response.status_code == 404, (method, path, response.text)
    assert (await env.b.get("/api/chats")).json() == []
    # Another vault's private character cannot be chatted with either.
    stolen = await env.b.post("/api/chats", json={"character_id": character_id})
    assert stolen.status_code == 404
    assert (await env.a.get(f"/api/chats/{cid}")).status_code == 200  # untouched


async def test_presets_crud_isolation_and_use(env: ChatEnv) -> None:
    body = {"agent": "writer", "name": "Của tôi", "layers": {"system": "Bạn là {{char}}, nói chuyện với {{user}}."}}
    created = await env.a.post("/api/presets", json=body)
    assert created.status_code == 201
    preset_id = created.json()["id"]
    assert [p["id"] for p in (await env.a.get("/api/presets")).json()] == [preset_id]
    assert (await env.a.get("/api/presets?agent=director")).json() == []
    assert (await env.b.get(f"/api/presets/{preset_id}")).status_code == 404
    assert (await env.b.put(f"/api/presets/{preset_id}", json=body)).status_code == 404
    assert (await env.b.delete(f"/api/presets/{preset_id}")).status_code == 404

    chat = await make_chat(env.a, await make_character(env.a))
    preview = (await env.a.get(f"/api/chats/{chat['id']}/prompt-preview")).json()
    assert preview["layers"][0]["text"] == "Bạn là Mai, nói chuyện với người chơi."

    updated = await env.a.put(f"/api/presets/{preset_id}", json={**body, "name": "Đổi"})
    assert updated.status_code == 200 and updated.json()["name"] == "Đổi"
    assert (await env.a.delete(f"/api/presets/{preset_id}")).status_code == 204
    assert (await env.a.get(f"/api/presets/{preset_id}")).status_code == 404


async def test_utility_routes(env: ChatEnv) -> None:
    models = (await env.a.get("/api/models")).json()
    assert {m["id"] for m in models} >= {"microsoft/microsoft-decision-1"}
    assert all({"id", "name", "context_length"} <= set(m) for m in models)
    counted = (await env.a.post("/api/tokens/count", json={"text": "Xin chào các bạn"})).json()
    assert counted["tokens"] > 0
    chat = await make_chat(env.a, await make_character(env.a))
    assert (await env.a.get(f"/api/usage?chat_id={chat['id']}")).json() == []
    persona_id = await make_persona(env.a)
    assert (await env.a.patch(f"/api/chats/{chat['id']}", json={"persona_id": persona_id})).json()[
        "persona_id"
    ] == persona_id
    assert (await env.a.patch(f"/api/chats/{chat['id']}", json={"persona_id": persona_id})).status_code == 200
    assert (await env.b.patch(f"/api/chats/{chat['id']}", json={"persona_id": persona_id})).status_code == 404
