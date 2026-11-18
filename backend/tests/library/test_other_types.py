from __future__ import annotations

from tests.library.conftest import LibEnv
from tests.library.helpers import lorebook, persona, post_card, tiny_png, upload, world


async def test_world_crud_and_isolation(env: LibEnv) -> None:
    created = await env.a.post("/api/worlds", json={"data": world(), "visibility": "private"})
    assert created.status_code == 201
    body = created.json()["world"]
    assert body["cover_url"] is None and body["needs_age"] is False
    assert body["tagline"] == "Thế giới yên bình." and body["tags"] == ["modern"]
    wid = body["id"]

    assert (await env.b.get(f"/api/worlds/{wid}")).status_code == 404
    listing = (await env.a.get("/api/worlds")).json()
    assert [i["id"] for i in listing["items"]] == [wid]

    bad = world(locations=[{"id": "c", "parent_id": "nope", "level": "province", "name": "x"}])
    response = await env.a.put(f"/api/worlds/{wid}", json={"data": bad, "visibility": "private"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "validation_error"

    response = await env.a.put(f"/api/worlds/{wid}", json={"data": world("Mới"), "visibility": "public"})
    assert response.json()["world"]["name"] == "Mới"
    assert (await env.b.get(f"/api/worlds/{wid}")).json()["world"]["is_owner"] is False
    assert (await env.b.delete(f"/api/worlds/{wid}")).status_code == 404

    cover = await env.a.put(f"/api/worlds/{wid}/cover", **upload(tiny_png()))
    assert cover.status_code == 200 and cover.json()["world"]["cover_url"]
    copy = (await env.b.post(f"/api/worlds/{wid}/duplicate")).json()["world"]
    assert copy["visibility"] == "private" and copy["cover_url"]

    # Worlds export as vietrp json only.
    ok = await env.a.get(f"/api/worlds/{wid}/export")
    assert ok.status_code == 200 and "attachment" in ok.headers["content-disposition"]
    assert (await env.a.get(f"/api/worlds/{wid}/export?format=ccv2")).status_code == 422
    assert (await env.a.delete(f"/api/worlds/{wid}")).status_code == 204


async def test_persona_crud(env: LibEnv) -> None:
    created = await env.a.post("/api/personas", json={"data": persona()})
    assert created.status_code == 201
    pid = created.json()["persona"]["id"]
    assert (await env.b.get(f"/api/personas/{pid}")).status_code == 404
    assert (await env.b.get("/api/personas")).json() == {"items": []}
    assert [p["id"] for p in (await env.a.get("/api/personas")).json()["items"]] == [pid]

    updated = await env.a.put(f"/api/personas/{pid}", json={"data": persona("Hùng")})
    assert updated.json()["persona"]["data"]["name"] == "Hùng"
    assert (await env.a.put(f"/api/personas/{pid}", json={"data": {"name": ""}})).status_code == 422
    assert (await env.b.put(f"/api/personas/{pid}", json={"data": persona()})).status_code == 404

    avatar = await env.a.put(f"/api/personas/{pid}/avatar", **upload(tiny_png()))
    url = avatar.json()["persona"]["avatar_url"]
    assert url and (await env.a.get(url)).status_code == 200
    assert (await env.b.get(url)).status_code == 404  # persona avatars are never public
    cleared = await env.a.delete(f"/api/personas/{pid}/avatar")
    assert cleared.json()["persona"]["avatar_url"] is None

    assert (await env.b.delete(f"/api/personas/{pid}")).status_code == 404
    assert (await env.a.delete(f"/api/personas/{pid}")).status_code == 204
    assert (await env.a.get(f"/api/personas/{pid}")).status_code == 404


async def test_lorebook_crud_duplicate_export(env: LibEnv) -> None:
    created = await env.a.post("/api/lorebooks", json={"data": lorebook(), "visibility": "private"})
    assert created.status_code == 201
    body = created.json()["lorebook"]
    lid = body["id"]
    assert body["entry_count"] == 1 and body["is_owner"] is True
    assert body["data"]["entries"][0]["id"] == "e1" and body["data"]["name"] == "Sổ tay"

    summary = (await env.a.get("/api/lorebooks")).json()
    assert summary["items"][0]["entry_count"] == 1 and "data" not in summary["items"][0]
    assert (await env.a.get("/api/lorebooks?q=zzz")).json()["items"] == []
    assert (await env.b.get(f"/api/lorebooks/{lid}")).status_code == 404

    two = lorebook(entries=[{"id": "a", "content": "x"}, {"id": "b", "content": "y"}])
    updated = await env.a.put(f"/api/lorebooks/{lid}", json={"data": two, "visibility": "public"})
    assert updated.json()["lorebook"]["entry_count"] == 2
    assert [e["id"] for e in updated.json()["lorebook"]["data"]["entries"]] == ["a", "b"]
    assert (await env.b.get(f"/api/lorebooks/{lid}")).json()["lorebook"]["is_owner"] is False
    assert (await env.b.put(f"/api/lorebooks/{lid}", json={"data": two, "visibility": "private"})).status_code == 404
    assert (await env.b.delete(f"/api/lorebooks/{lid}")).status_code == 404

    dup = (await env.b.post(f"/api/lorebooks/{lid}/duplicate")).json()["lorebook"]
    assert dup["id"] != lid and dup["visibility"] == "private" and dup["entry_count"] == 2

    duplicate_ids = lorebook(entries=[{"id": "a"}, {"id": "a"}])
    assert (await env.a.post("/api/lorebooks", json={"data": duplicate_ids})).status_code == 422

    for fmt in ("vietrp", "st"):
        export = await env.a.get(f"/api/lorebooks/{lid}/export?format={fmt}")
        assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
    assert (await env.a.get(f"/api/lorebooks/{lid}/export?format=bogus")).status_code == 422
    assert (await env.a.delete(f"/api/lorebooks/{lid}")).status_code == 204
    assert (await env.a.get(f"/api/lorebooks/{lid}")).status_code == 404


async def test_gallery_and_favorites(env: LibEnv) -> None:
    await post_card(env.a, "public", name="Mine")
    theirs = await post_card(env.b, "public", name="Theirs", tags=["magic"])
    await post_card(env.b, "private", name="Hidden")

    gallery = (await env.a.get("/api/gallery?type=character")).json()
    names = [i["name"] for i in gallery["items"]]
    assert names == ["Theirs", "Mine"]  # public items of every vault, newest first, private never
    first = gallery["items"][0]
    assert first["type"] == "character" and first["is_owner"] is False and first["is_favorite"] is False
    assert first["favorite_count"] == 0 and first["author"].startswith("Bob") and first["image_url"] is None
    assert [i["name"] for i in (await env.a.get("/api/gallery?q=thei")).json()["items"]] == ["Theirs"]
    assert [i["name"] for i in (await env.a.get("/api/gallery?tag=magic")).json()["items"]] == ["Theirs"]

    # Favorites: idempotent put, visible only for visible targets.
    assert (await env.a.put(f"/api/favorites/character/{theirs['id']}")).status_code == 204
    assert (await env.a.put(f"/api/favorites/character/{theirs['id']}")).status_code == 204
    assert (await env.b.put(f"/api/favorites/character/{theirs['id']}")).status_code == 204
    assert (await env.a.put("/api/favorites/character/11111111-1111-4111-8111-111111111111")).status_code == 404
    assert (await env.a.put(f"/api/favorites/bogus/{theirs['id']}")).status_code == 422

    favs = (await env.a.get("/api/favorites")).json()["items"]
    assert [i["id"] for i in favs] == [theirs["id"]]
    assert favs[0]["is_favorite"] is True and favs[0]["favorite_count"] == 2

    by_fav = (await env.a.get("/api/gallery?sort=favorites&limit=1")).json()
    assert [i["name"] for i in by_fav["items"]] == ["Theirs"] and by_fav["next_cursor"]
    second = (await env.a.get(f"/api/gallery?sort=favorites&limit=1&cursor={by_fav['next_cursor']}")).json()
    assert [i["name"] for i in second["items"]] == ["Mine"] and second["next_cursor"] is None

    recent = (await env.a.get("/api/gallery?limit=1")).json()
    page2 = (await env.a.get(f"/api/gallery?limit=1&cursor={recent['next_cursor']}")).json()
    assert [i["name"] for i in recent["items"] + page2["items"]] == ["Theirs", "Mine"]

    assert (await env.a.delete(f"/api/favorites/character/{theirs['id']}")).status_code == 204
    assert (await env.a.delete(f"/api/favorites/character/{theirs['id']}")).status_code == 204
    assert (await env.a.get("/api/favorites")).json()["items"] == []
    assert (await env.a.delete("/api/favorites/character/11111111-1111-4111-8111-111111111111")).status_code == 404

    # Worlds appear under type=world, and a deleted item drops out of everyone's favorites.
    w = (await env.b.post("/api/worlds", json={"data": world(), "visibility": "public"})).json()["world"]
    assert [i["id"] for i in (await env.a.get("/api/gallery?type=world")).json()["items"]] == [w["id"]]
    assert (await env.a.put(f"/api/favorites/world/{w['id']}")).status_code == 204
    assert (await env.b.delete(f"/api/worlds/{w['id']}")).status_code == 204
    assert (await env.a.get("/api/favorites")).json()["items"] == []
