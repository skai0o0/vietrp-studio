from __future__ import annotations

import httpx

from tests.library.conftest import LibEnv
from tests.library.helpers import card, lorebook, post_card, tiny_png, upload


async def test_locked_routes_return_401(env: LibEnv) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as anon:
        for method, path in [
            ("GET", "/api/characters"),
            ("GET", "/api/worlds"),
            ("GET", "/api/personas"),
            ("GET", "/api/lorebooks"),
            ("GET", "/api/gallery"),
            ("GET", "/api/favorites"),
            ("GET", "/api/assets/00000000-0000-0000-0000-000000000000"),
            ("POST", "/api/import"),
        ]:
            response = await anon.request(method, path)
            assert response.status_code == 401, path
            assert response.json()["error"]["code"] == "vault_locked"


async def test_character_crud(env: LibEnv) -> None:
    created = await post_card(env.a, name="Lan")
    assert created["is_owner"] is True and created["visibility"] == "private"
    assert created["needs_age"] is False and created["avatar_url"] is None and created["author"].startswith("Alice")
    assert created["data"]["name"] == "Lan"
    item_id = created["id"]

    got = (await env.a.get(f"/api/characters/{item_id}")).json()["character"]
    assert got["id"] == item_id and got["tagline"] == "Lan tagline" and got["tags"] == ["slice"]

    listing = (await env.a.get("/api/characters")).json()
    assert listing["next_cursor"] is None
    assert [i["id"] for i in listing["items"]] == [item_id]
    assert "data" not in listing["items"][0]

    updated = await env.a.put(
        f"/api/characters/{item_id}", json={"data": card("Lan Anh", age=30), "visibility": "public"}
    )
    assert updated.status_code == 200
    assert updated.json()["character"]["name"] == "Lan Anh"
    assert updated.json()["character"]["visibility"] == "public"

    assert (await env.a.delete(f"/api/characters/{item_id}")).status_code == 204
    assert (await env.a.get(f"/api/characters/{item_id}")).status_code == 404
    assert (await env.a.delete(f"/api/characters/{item_id}")).status_code == 404


async def test_search_and_tag_filters(env: LibEnv) -> None:
    await post_card(env.a, name="Alpha", tags=["x"])
    await post_card(env.a, name="Beta_100%", tags=["y"], tagline="")
    assert [i["name"] for i in (await env.a.get("/api/characters?q=alp")).json()["items"]] == ["Alpha"]
    assert [i["name"] for i in (await env.a.get("/api/characters?q=a_1")).json()["items"]] == ["Beta_100%"]
    assert (await env.a.get("/api/characters?q=_")).json()["items"][0]["name"] == "Beta_100%"
    assert (await env.a.get("/api/characters?q=%25")).json()["items"][0]["name"] == "Beta_100%"
    assert [i["name"] for i in (await env.a.get("/api/characters?tag=Y")).json()["items"]] == ["Beta_100%"]


async def test_validation_errors(env: LibEnv) -> None:
    no_age = card()
    del no_age["age"]
    for data in (no_age, card(name=""), {"format": "vietrp-card", "bogus": 1}):
        response = await env.a.post("/api/characters", json={"data": data, "visibility": "private"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    response = await env.a.post("/api/characters", json={"data": card(), "visibility": "friends"})
    assert response.status_code == 422


async def test_isolation_matrix(env: LibEnv) -> None:
    private = await post_card(env.a, name="Secret")
    public = await post_card(env.a, "public", name="Open")
    pid, oid = private["id"], public["id"]

    # Another vault's private item looks like it does not exist, whatever the verb.
    assert (await env.b.get(f"/api/characters/{pid}")).status_code == 404
    assert (await env.b.put(f"/api/characters/{pid}", json={"data": card(), "visibility": "public"})).status_code == 404
    assert (await env.b.delete(f"/api/characters/{pid}")).status_code == 404
    assert (await env.b.post(f"/api/characters/{pid}/duplicate")).status_code == 404
    assert (await env.b.get(f"/api/characters/{pid}/export")).status_code == 404
    assert (await env.b.put(f"/api/favorites/character/{pid}")).status_code == 404
    assert (await env.b.get("/api/characters")).json()["items"] == []

    # A public item is readable but read-only.
    seen = (await env.b.get(f"/api/characters/{oid}")).json()["character"]
    assert seen["is_owner"] is False and seen["author"].startswith("Alice")
    assert (
        await env.b.put(f"/api/characters/{oid}", json={"data": card("Hijack"), "visibility": "private"})
    ).status_code == 404
    assert (await env.b.delete(f"/api/characters/{oid}")).status_code == 404
    assert (await env.a.get(f"/api/characters/{oid}")).json()["character"]["name"] == "Open"
    assert (await env.b.get("/api/characters")).json()["items"] == []  # own vault only

    # Duplicating a public item yields a private copy owned by the caller.
    copy = (await env.b.post(f"/api/characters/{oid}/duplicate")).json()["character"]
    assert copy["id"] != oid and copy["visibility"] == "private" and copy["is_owner"] is True
    assert [i["id"] for i in (await env.b.get("/api/characters")).json()["items"]] == [copy["id"]]


async def test_nsfw_minor_public_guard(env: LibEnv) -> None:
    minor_nsfw = card(age=16, tags=["nsfw"])
    response = await env.a.post("/api/characters", json={"data": minor_nsfw, "visibility": "public"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "nsfw_minor_public"
    assert (await env.a.post("/api/characters", json={"data": minor_nsfw, "visibility": "private"})).status_code == 201
    assert (
        await env.a.post("/api/characters", json={"data": card(age=18, tags=["nsfw"]), "visibility": "public"})
    ).status_code == 201
    assert (
        await env.a.post("/api/characters", json={"data": card(age=16, tags=["slice"]), "visibility": "public"})
    ).status_code == 201

    # Publishing an existing private minor+nsfw card through PUT is blocked too.
    private = (await env.a.post("/api/characters", json={"data": minor_nsfw, "visibility": "private"})).json()
    response = await env.a.put(
        f"/api/characters/{private['character']['id']}", json={"data": minor_nsfw, "visibility": "public"}
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "nsfw_minor_public"


async def test_lorebook_links_follow_lorebook_ids(env: LibEnv) -> None:
    book1 = (await env.a.post("/api/lorebooks", json={"data": lorebook("One"), "visibility": "private"})).json()
    book2 = (await env.a.post("/api/lorebooks", json={"data": lorebook("Two"), "visibility": "private"})).json()
    id1, id2 = book1["lorebook"]["id"], book2["lorebook"]["id"]
    missing = "11111111-1111-4111-8111-111111111111"

    created = await env.a.post(
        "/api/characters", json={"data": card(lorebook_ids=[id1, missing]), "visibility": "private"}
    )
    body = created.json()["character"]
    assert await env.links_of(body["id"]) == {id1}
    assert [w["code"] for w in body["warnings"] if w["path"] == "lorebook_ids"] == ["lorebook_not_found"]

    updated = await env.a.put(
        f"/api/characters/{body['id']}", json={"data": card(lorebook_ids=[id2]), "visibility": "private"}
    )
    assert updated.status_code == 200
    assert await env.links_of(body["id"]) == {id2}

    # Another vault's private lorebook cannot be linked.
    other = (await env.b.post("/api/lorebooks", json={"data": lorebook("Theirs"), "visibility": "private"})).json()
    await env.a.put(
        f"/api/characters/{body['id']}",
        json={"data": card(lorebook_ids=[other["lorebook"]["id"]]), "visibility": "private"},
    )
    assert await env.links_of(body["id"]) == set()

    await env.a.put(
        f"/api/characters/{body['id']}", json={"data": card(lorebook_ids=[id1, id2]), "visibility": "private"}
    )
    assert await env.links_of(body["id"]) == {id1, id2}
    await env.a.delete(f"/api/characters/{body['id']}")
    assert await env.links_of(body["id"]) == set()


async def test_cursor_pagination(env: LibEnv) -> None:
    ids = [(await post_card(env.a, name=f"Card {n}"))["id"] for n in range(5)]
    seen: list[str] = []
    cursor = None
    pages = 0
    while True:
        url = "/api/characters?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = (await env.a.get(url)).json()
        seen.extend(i["id"] for i in page["items"])
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert pages == 3
    # Every item exactly once. Exact order is not asserted: cards created in the same clock tick share
    # updated_at, and the repository then breaks the tie by id (random UUID), which is still a stable order.
    assert len(seen) == len(set(seen)) == len(ids)
    assert set(seen) == set(ids)
    assert (await env.a.get("/api/characters?cursor=not-a-cursor")).status_code == 422
    assert (await env.a.get("/api/characters?limit=101")).status_code == 422
    assert (await env.a.get("/api/characters?limit=0")).status_code == 422


async def test_avatar_upload_and_asset_access_rules(env: LibEnv) -> None:
    item = await post_card(env.a)
    item_id = item["id"]

    response = await env.a.put(f"/api/characters/{item_id}/avatar", **upload(tiny_png()))
    assert response.status_code == 200, response.text
    url = response.json()["character"]["avatar_url"]
    assert url.startswith("/api/assets/")

    owned = await env.a.get(url)
    assert owned.status_code == 200 and owned.content == tiny_png()
    assert owned.headers["content-type"] == "image/png"
    assert owned.headers["cache-control"] == "private, max-age=86400"

    # Private item: another vault cannot read the image.
    assert (await env.b.get(url)).status_code == 404

    # Public item: any unlocked vault can.
    await env.a.put(f"/api/characters/{item_id}", json={"data": card(), "visibility": "public"})
    assert (await env.b.get(url)).status_code == 200

    # Duplicating copies the image into the new owner's vault.
    copy = (await env.b.post(f"/api/characters/{item_id}/duplicate")).json()["character"]
    assert copy["avatar_url"] and copy["avatar_url"] != url
    await env.a.put(f"/api/characters/{item_id}", json={"data": card(), "visibility": "private"})
    assert (await env.b.get(url)).status_code == 404
    assert (await env.b.get(copy["avatar_url"])).status_code == 200

    # Replacing the avatar removes the old asset; removing it clears the url.
    replaced = (await env.a.put(f"/api/characters/{item_id}/avatar", **upload(tiny_png()))).json()["character"]
    assert replaced["avatar_url"] != url
    assert (await env.a.get(url)).status_code == 404
    cleared = await env.a.delete(f"/api/characters/{item_id}/avatar")
    assert cleared.json()["character"]["avatar_url"] is None

    # Another vault cannot touch the avatar.
    assert (await env.b.put(f"/api/characters/{item_id}/avatar", **upload(tiny_png()))).status_code == 404
    assert (await env.b.delete(f"/api/characters/{item_id}/avatar")).status_code == 404


async def test_avatar_rejections(env: LibEnv) -> None:
    item = await post_card(env.a)
    path = f"/api/characters/{item['id']}/avatar"
    bad = await env.a.put(path, **upload(b"GIF89a not allowed"))
    assert bad.status_code == 415 and bad.json()["error"]["code"] == "unsupported_media"
    big = await env.a.put(path, **upload(tiny_png() + b"\0" * (5 * 1024 * 1024)))
    assert big.status_code == 413 and big.json()["error"]["code"] == "file_too_large"
    assert (await env.a.put(path, content=b"")).status_code == 422
    unknown = await env.a.get("/api/assets/00000000-0000-4000-8000-000000000000")
    assert unknown.status_code == 404
