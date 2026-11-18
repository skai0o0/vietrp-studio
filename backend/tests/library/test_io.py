from __future__ import annotations

import json
from typing import Any

import httpx

from tests.library.conftest import LibEnv
from tests.library.helpers import card, lorebook, post_card, tiny_png, upload, world


async def _import(client: httpx.AsyncClient, content: bytes, filename: str) -> httpx.Response:
    return await client.post("/api/import", **upload(content, filename))


def _comparable(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k != "lorebook_ids"}


async def test_vietrp_json_round_trip(env: LibEnv) -> None:
    original = await post_card(env.a, name="Round Trip", greetings=["Chào", "Hi"], tags=["a", "b"])
    exported = await env.a.get(f"/api/characters/{original['id']}/export?format=vietrp&as=json")
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]

    imported = await _import(env.a, exported.content, "card.json")
    assert imported.status_code == 201, imported.text
    body = imported.json()
    assert body["kind"] == "character" and body["needs_age"] is False
    assert "world" not in body and "lorebook" not in body
    assert body["character"]["id"] != original["id"] and body["character"]["visibility"] == "private"
    assert body["character"]["data"] == original["data"]


async def test_st_round_trip_with_lorebook_and_png_avatar(env: LibEnv) -> None:
    book = (await env.a.post("/api/lorebooks", json={"data": lorebook("Linked"), "visibility": "private"})).json()
    original = (
        await env.a.post(
            "/api/characters",
            json={"data": card("Hoa", lorebook_ids=[book["lorebook"]["id"]]), "visibility": "private"},
        )
    ).json()["character"]
    assert (await env.a.put(f"/api/characters/{original['id']}/avatar", **upload(tiny_png()))).status_code == 200

    for fmt, as_, filename in [
        ("ccv2", "json", "a.json"),
        ("ccv3", "json", "a.json"),
        ("ccv2", "png", "a.png"),
        ("ccv3", "png", "a.png"),
    ]:
        exported = await env.a.get(f"/api/characters/{original['id']}/export?format={fmt}&as={as_}")
        assert exported.status_code == 200, exported.text
        imported = await _import(env.a, exported.content, filename)
        assert imported.status_code == 201, imported.text
        body = imported.json()
        assert body["character"]["data"]["name"] == "Hoa"
        assert _comparable(body["character"]["data"]) == _comparable(original["data"])
        assert body["character"]["needs_age"] is False
        # The embedded character book comes back as its own private lorebook, linked to the card.
        assert body["lorebook"]["data"]["entries"][0]["content"] == "Thanh kiếm cổ."
        assert body["character"]["data"]["lorebook_ids"][-1] == body["lorebook"]["id"]
        assert body["lorebook"]["is_owner"] is True
        if as_ == "png":
            assert body["character"]["avatar_url"]


async def test_non_png_avatar_exports_with_placeholder(env: LibEnv) -> None:
    item = await post_card(env.a)
    jpeg = b"\xff\xd8\xff\xe0" + b"\0" * 32
    assert (await env.a.put(f"/api/characters/{item['id']}/avatar", **upload(jpeg, "a.jpg"))).status_code == 200
    exported = await env.a.get(f"/api/characters/{item['id']}/export?format=ccv3&as=png")
    assert exported.status_code == 200 and exported.content.startswith(b"\x89PNG")
    assert (await env.a.get(f"/api/characters/{item['id']}/export?format=vietrp&as=png")).status_code >= 400


async def test_import_card_without_age_needs_age(env: LibEnv) -> None:
    raw = json.dumps({"name": "Bare", "description": "Một nhân vật", "first_mes": "Xin chào"}).encode()
    response = await _import(env.a, raw, "bare.json")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["needs_age"] is True
    character = body["character"]
    assert character["needs_age"] is True and character["data"]["age"] is None
    assert character["data"]["is_fictional"] is True
    assert any(w["code"] == "age_missing" for w in character["warnings"] + body["warnings"])

    # Stays flagged until edited with an age; an edit without one is refused.
    listed = (await env.a.get("/api/characters")).json()["items"][0]
    assert listed["needs_age"] is True
    without = await env.a.put(
        f"/api/characters/{character['id']}", json={"data": character["data"], "visibility": "private"}
    )
    assert without.status_code == 422
    fixed = {**character["data"], "age": 22}
    ok = await env.a.put(f"/api/characters/{character['id']}", json={"data": fixed, "visibility": "private"})
    assert ok.status_code == 200 and ok.json()["character"]["needs_age"] is False


async def test_import_world_and_lorebook(env: LibEnv) -> None:
    created = (await env.a.post("/api/worlds", json={"data": world(), "visibility": "private"})).json()["world"]
    exported = await env.a.get(f"/api/worlds/{created['id']}/export")
    imported = (await _import(env.a, exported.content, "w.json")).json()
    assert imported["kind"] == "world" and imported["needs_age"] is False
    assert imported["world"]["data"] == created["data"] and imported["world"]["id"] != created["id"]

    book = (await env.a.post("/api/lorebooks", json={"data": lorebook(), "visibility": "private"})).json()["lorebook"]
    for fmt in ("vietrp", "st"):
        exported = await env.a.get(f"/api/lorebooks/{book['id']}/export?format={fmt}")
        result = (await _import(env.b, exported.content, "book.json")).json()
        assert result["kind"] == "lorebook"
        assert result["lorebook"]["data"]["entries"][0]["content"] == "Thanh kiếm cổ."
        assert result["lorebook"]["is_owner"] is True


async def test_import_rejections(env: LibEnv) -> None:
    unknown = await _import(env.a, b'{"hello": "world"}', "x.json")
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "format_unknown"
    assert (await _import(env.a, b"not json at all", "x.json")).status_code == 422
    media = await _import(env.a, b"{}", "x.txt")
    assert media.status_code == 415 and media.json()["error"]["code"] == "unsupported_media"
    big = await _import(env.a, b" " * (20 * 1024 * 1024 + 1), "x.json")
    assert big.status_code == 413 and big.json()["error"]["code"] == "file_too_large"
    assert (await env.a.post("/api/import", content=b"")).status_code == 422
    assert (await env.a.get("/api/characters")).json()["items"] == []
