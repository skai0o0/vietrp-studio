"""P1 review fixes: nsfw bypasses, import transaction, avatar stripping, upload cap, cursors."""

from __future__ import annotations

import base64
import json
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.core.errors import AppError
from app.formats.png import read_text_chunks, write_text_chunks
from app.repositories.characters_repo import Cursor, InvalidCursorError, decode_cursor, encode_cursor
from app.services.io_service import IoService
from app.services.library_service import CHARACTER_KIND, LibraryService
from tests.library.conftest import LibEnv
from tests.library.fakes import FakeStore, make_fake_repos
from tests.library.helpers import card, lorebook, post_card, tiny_png, upload, world
from tests.vault.fakes import FakeVaultRepository


async def _import(client: httpx.AsyncClient, content: bytes, filename: str) -> httpx.Response:
    return await client.post("/api/import", **upload(content, filename))


# --- B2 ---


@pytest.mark.parametrize("tag", ["nsfw ", "nsfw​", "ｎｓｆｗ", "18+", "nsfw_x", "r-18", "adult"])
async def test_nsfw_variants_cannot_bypass_minor_public_guard(env: LibEnv, tag: str) -> None:
    data = card(age=16, tags=[tag])
    response = await env.a.post("/api/characters", json={"data": data, "visibility": "public"})
    assert response.status_code == 422 and response.json()["error"]["code"] == "nsfw_minor_public"
    private = await env.a.post("/api/characters", json={"data": data, "visibility": "private"})
    assert private.status_code == 201
    assert private.json()["character"]["data"]["tags"][0] in {"nsfw", "18+", "nsfw_x", "r-18", "adult"}


def test_public_nsfw_card_with_unknown_age_is_blocked() -> None:
    data = card(age=None, tags=["nsfw"])
    with pytest.raises(AppError) as exc:
        CHARACTER_KIND.validate(data, "public", True)
    assert exc.value.code == "nsfw_minor_public"
    CHARACTER_KIND.validate(data, "private", True)  # private stays allowed


async def test_world_tags_are_normalized_over_api(env: LibEnv) -> None:
    response = await env.a.post("/api/worlds", json={"data": world(tags=["ｍｏｄｅｒｎ "]), "visibility": "private"})
    assert response.status_code == 201
    assert response.json()["world"]["data"]["tags"] == ["modern"]


# --- M1 ---


async def test_same_vault_reimport_links_exactly_one_lorebook(env: LibEnv) -> None:
    book = (await env.a.post("/api/lorebooks", json={"data": lorebook("Linked"), "visibility": "private"})).json()
    original = (
        await env.a.post(
            "/api/characters",
            json={"data": card("Hoa", lorebook_ids=[book["lorebook"]["id"]]), "visibility": "private"},
        )
    ).json()["character"]
    for fmt in ("vietrp", "ccv2", "ccv3"):
        exported = await env.a.get(f"/api/characters/{original['id']}/export?format={fmt}&as=json")
        assert exported.status_code == 200
        body = (await _import(env.a, exported.content, "a.json")).json()
        ids = body["character"]["data"]["lorebook_ids"]
        # Native vietrp JSON carries only ids (kept); ST exports embed a merged copy that replaces them.
        assert ids == ([book["lorebook"]["id"]] if fmt == "vietrp" else [body["lorebook"]["id"]])
        assert await env.links_of(body["character"]["id"]) == set(ids)


# --- M2 ---


def _fake_service() -> tuple[IoService, uuid.UUID, list[int]]:
    store = FakeStore(FakeVaultRepository())
    vault_id = uuid.uuid4()
    store.vaults.rows[vault_id] = type("V", (), {"display_name": "V"})()  # type: ignore[assignment]
    repos = make_fake_repos(store)
    commits: list[int] = []
    real_commit = repos.characters.commit

    async def counting_commit() -> None:
        commits.append(1)
        await real_commit()

    repos.characters.commit = counting_commit  # type: ignore[method-assign]
    return IoService(LibraryService(repos)), vault_id, commits


_ENVELOPE = {
    "spec": "chara_card_v2",
    "data": {"name": "A", "description": "20 tuổi", "character_book": {"entries": [{"keys": ["k"], "content": "c"}]}},
}


async def test_failed_card_create_commits_nothing() -> None:
    service, vault_id, commits = _fake_service()

    async def failing_create(*_a: object, **_k: object) -> object:
        raise RuntimeError("boom")

    service._repos.characters.create = failing_create  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await service.import_upload(vault_id, "a.json", json.dumps(_ENVELOPE).encode())
    # The lorebook was written to the open session but never committed (the request session rolls back).
    assert commits == []


async def test_card_with_embedded_lorebook_commits_once() -> None:
    service, vault_id, commits = _fake_service()
    result = await service.import_upload(vault_id, "a.json", json.dumps(_ENVELOPE).encode())
    assert result.lorebook is not None and result.character is not None
    assert len(commits) == 1


# --- m1 ---


async def test_imported_png_avatar_has_no_text_chunks(env: LibEnv) -> None:
    payload = {"spec": "chara_card_v2", "data": {"name": "Png", "description": "20 tuổi", "first_mes": "Chào"}}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    png = write_text_chunks(tiny_png(), {"chara": encoded})
    response = await _import(env.a, png, "png.png")
    assert response.status_code == 201, response.text
    url = response.json()["character"]["avatar_url"]
    stored = await env.a.get(url)
    assert stored.status_code == 200 and stored.content.startswith(b"\x89PNG")
    assert read_text_chunks(stored.content) == {}
    assert encoded.encode() not in stored.content


# --- m2 ---


async def test_oversized_content_length_rejected_before_body_is_read(env: LibEnv) -> None:
    headers = {"content-type": "multipart/form-data; boundary=xyz", "content-length": str(30 * 1024 * 1024)}
    response = await env.a.post("/api/import", content=b"--xyz--", headers=headers)
    assert response.status_code == 413 and response.json()["error"]["code"] == "file_too_large"
    item = await post_card(env.a)
    headers["content-length"] = str(6 * 1024 * 1024)
    response = await env.a.put(f"/api/characters/{item['id']}/avatar", content=b"--xyz--", headers=headers)
    assert response.status_code == 413 and response.json()["error"]["code"] == "file_too_large"


# --- m4 ---


def _b64(payload: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def test_decode_cursor_bounds() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    uid = uuid.uuid4()
    assert decode_cursor(encode_cursor(Cursor(now, uid, 5))).count == 5
    for bad in (-1, 2**31, True, 1.5, "7"):
        with pytest.raises(InvalidCursorError):
            decode_cursor(_b64({"u": now.isoformat(), "i": str(uid), "c": bad}))
    for payload in (
        {"u": "nope", "i": str(uid), "c": None},
        {"u": now.isoformat(), "i": 5, "c": None},
        {"u": 5, "i": str(uid), "c": None},
        [1, 2],
        "text",
    ):
        with pytest.raises(InvalidCursorError):
            decode_cursor(_b64(payload))


async def test_favorites_sort_rejects_cursor_without_count(env: LibEnv) -> None:
    await post_card(env.b, "public", name="One")
    await post_card(env.b, "public", name="Two")
    page = (await env.a.get("/api/gallery?limit=1")).json()
    assert page["next_cursor"]
    response = await env.a.get(f"/api/gallery?sort=favorites&cursor={page['next_cursor']}")
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_cursor"
    bad = _b64({"u": "2026-01-01T00:00:00+00:00", "i": str(uuid.uuid4()), "c": 2**40})
    response = await env.a.get(f"/api/gallery?sort=favorites&cursor={bad}")
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_cursor"
