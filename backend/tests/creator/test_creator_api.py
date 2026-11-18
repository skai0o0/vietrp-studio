"""End-to-end API tests for Creator endpoints and Library `/judge` routes (Fake + PostgreSQL)."""

from __future__ import annotations

import json
import os
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents import card_judge
from app.agents.base import LLMGateway
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.deps import GatewayFactory, SessionStoreDep, SettingsDep, get_gateway_factory
from app.core.errors import AppError
from app.core.sessions import VaultSession
from app.creator import card_defaults, world_defaults
from app.formats.world import LEVEL_ORDER
from app.llm.config import LLMConfig
from app.llm.deps import build_llm_services
from app.llm.fake import RecordedLLM
from app.main import create_app
from app.models import Base
from app.models.vault import Vault
from app.repositories.creator_repo import SqlCreatorRepository
from app.services.asset_service import get_asset_repo
from app.services.creator_service import CreatorRepos, CreatorUow, get_creator_uow
from app.services.library_service import get_repos
from app.services.turn_service import get_key_check
from app.services.vault_service import VaultService, get_vault_service
from tests.conftest import make_settings
from tests.library.fakes import FakeCreatorRepository, FakeStore, make_fake_repos
from tests.llm.helpers import FAKE_KEY, FakeRecorder
from tests.vault.conftest import FAST_ARGON2
from tests.vault.fakes import FakeSecretRepository, FakeVaultRepository

TEST_DATABASE_URL = os.environ.get("VIETRP_TEST_DATABASE_URL")

DECISIONS = "/api/alpha/decisions"
COMPLETIONS = "/api/v1/chat/completions"


@dataclass
class CreatorEnv:
    app: FastAPI
    a: httpx.AsyncClient
    b: httpx.AsyncClient
    llm: RecordedLLM
    recorder: FakeRecorder
    set_key_present: Callable[[bool], None]


def _settings() -> Settings:
    return make_settings(**FAST_ARGON2, unlock_rate_limit_attempts=10_000, sse_ping_interval_seconds=15)


async def _new_vault(client: httpx.AsyncClient, name: str) -> None:
    passphrase = f"creator test {secrets.token_hex(8)} passphrase"
    response = await client.post("/api/vault/create", json={"passphrase": passphrase, "display_name": name})
    assert response.status_code == 201, response.text


def _wire_llm(app: FastAPI, settings: Settings) -> tuple[RecordedLLM, FakeRecorder, Callable[[bool], None]]:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    recorder = FakeRecorder()
    cfg = LLMConfig(backoff_base_seconds=0.0, max_retries=1)
    app.state.llm_services = build_llm_services(settings, transport=llm.transport(), cfg=cfg)
    key_state = {"present": True}

    def gateway_factory() -> GatewayFactory:
        def build(vault_session: VaultSession, chat_id: uuid.UUID | None) -> LLMGateway:
            async def key() -> str:
                if not key_state["present"]:
                    raise AppError("openrouter_key_missing", "No OpenRouter API key is stored in this vault", 400)
                return FAKE_KEY

            return LLMGateway(
                app.state.llm_services,
                vault_id=vault_session.vault_id,
                chat_id=chat_id,
                api_key=key,
                recorder=recorder,
            )

        return build

    async def check_key(_session: VaultSession) -> None:
        if not key_state["present"]:
            raise AppError("openrouter_key_missing", "No OpenRouter API key is stored in this vault", 400)

    def set_key_present(present: bool) -> None:
        key_state["present"] = present

    app.dependency_overrides[get_gateway_factory] = gateway_factory
    app.dependency_overrides[get_key_check] = lambda: check_key
    return llm, recorder, set_key_present


async def _clients(app: FastAPI, tag: str) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient]]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as a,
        httpx.AsyncClient(transport=transport, base_url="http://test") as b,
    ):
        await _new_vault(a, f"Alice {tag}")
        await _new_vault(b, f"Bob {tag}")
        yield a, b


async def _fake_env() -> AsyncIterator[CreatorEnv]:
    settings = _settings()
    app = create_app(settings)
    vaults = FakeVaultRepository()
    store = FakeStore(vaults)
    library_repos = make_fake_repos(store)
    creator_repo = FakeCreatorRepository(store)

    def vault_service(session_store: SessionStoreDep, current: SettingsDep) -> VaultService:
        return VaultService(vaults, FakeSecretRepository(), session_store, current)

    @asynccontextmanager
    async def uow() -> AsyncIterator[CreatorRepos]:
        yield CreatorRepos(creator=creator_repo, library=library_repos, commit=library_repos.commit)

    fake_uow: CreatorUow = uow
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_vault_service] = vault_service
    app.dependency_overrides[get_repos] = lambda: library_repos
    app.dependency_overrides[get_asset_repo] = lambda: library_repos.assets
    app.dependency_overrides[get_creator_uow] = lambda: fake_uow
    llm, recorder, set_key_present = _wire_llm(app, settings)
    async for a, b in _clients(app, "fake"):
        yield CreatorEnv(app, a, b, llm, recorder, set_key_present)


async def _pg_env() -> AsyncIterator[CreatorEnv]:
    assert TEST_DATABASE_URL
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    settings = _settings()
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings

    async def db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    @asynccontextmanager
    async def uow() -> AsyncIterator[CreatorRepos]:
        async with sessionmaker() as db:
            yield CreatorRepos(creator=SqlCreatorRepository(db), library=get_repos(db), commit=db.commit)

    pg_uow: CreatorUow = uow
    app.dependency_overrides[get_session] = db_session
    app.dependency_overrides[get_creator_uow] = lambda: pg_uow
    llm, recorder, set_key_present = _wire_llm(app, settings)
    tag = secrets.token_hex(4)
    try:
        async for a, b in _clients(app, tag):
            yield CreatorEnv(app, a, b, llm, recorder, set_key_present)
    finally:
        async with sessionmaker() as session:
            await session.execute(delete(Vault).where(Vault.display_name.in_([f"Alice {tag}", f"Bob {tag}"])))
            await session.commit()
        await engine.dispose()


@pytest.fixture(params=["fake", "postgres"])
async def env(request: pytest.FixtureRequest) -> AsyncIterator[CreatorEnv]:
    if request.param == "postgres" and not TEST_DATABASE_URL:
        pytest.skip("VIETRP_TEST_DATABASE_URL is not set")
    factory = _fake_env if request.param == "fake" else _pg_env
    async for value in factory():
        yield value
        await value.app.state.llm_services.aclose()


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].strip() for line in block.split("\n") if line.startswith("data:"))
        if data:
            events.append(json.loads(data))
    return events


def _sse_reply(*parts: str) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = [{"id": "c1", "choices": [{"delta": {"role": "assistant", "content": ""}}]}]
    chunks += [{"id": "c1", "choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in parts]
    chunks.append({"id": "c1", "choices": [{"delta": {}, "finish_reason": "stop"}]})
    chunks.append({"id": "c1", "choices": [], "usage": {"prompt_tokens": 80, "completion_tokens": 16, "cost": 0.0001}})
    return {"status": 200, "sse": chunks}


def _completion(content: str) -> dict[str, Any]:
    return {
        "status": 200,
        "json": {
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 50, "cost": 0.0002},
        },
    }


def _judge_ok(score: float = 0.88) -> dict[str, Any]:
    return {
        "status": 200,
        "json": {
            "model": "microsoft/microsoft-decision-1",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.0001},
            "answers": {cid: {"noul": score} for cid in card_judge.CRITERIA},
        },
    }


async def test_pools_and_defaults_helper(env: CreatorEnv) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as anon:
        assert (await anon.get("/api/creator/pools")).status_code == 401

    resp = await env.a.get("/api/creator/pools")
    assert resp.status_code == 200
    body = resp.json()
    char_carousels = body["character"]["carousels"]
    char_slots = body["character"]["slots"]
    assert set(char_carousels) == {
        "personality_archetype",
        "backstory_premise",
        "goals",
        "speech_style",
        "format_trope",
    }
    assert set(char_slots) == {
        "gender",
        "age_range",
        "occupation",
        "hair",
        "eyes",
        "build",
        "zodiac",
        "hobby",
        "flaw",
        "signature_item",
    }
    assert all(len(v) >= 8 for v in char_carousels.values())
    assert all(len(v) >= 8 for v in char_slots.values())

    world_carousels = body["world"]["carousels"]
    world_slots = body["world"]["slots"]
    assert set(world_carousels) == {"world_rules", "genre_trope", "tone", "starting_situation"}
    assert set(world_slots) == {"era", "tech_level", "magic_level", "climate", "opening_place", "root_level"}
    assert world_slots["root_level"] == list(LEVEL_ORDER)

    assert card_defaults()["format"] == "vietrp-card"
    assert world_defaults()["format"] == "vietrp-world"


async def test_session_crud_and_cross_vault_isolation(env: CreatorEnv) -> None:
    created = await env.a.post(
        "/api/creator/sessions",
        json={"mode": "slots", "target_type": "character", "seed": {"occupation": "Pha chế"}},
    )
    assert created.status_code == 201, created.text
    sess = created.json()
    sid = sess["id"]
    assert sess["mode"] == "slots"
    assert sess["target_type"] == "character"
    assert sess["seed"]["target_type"] == "character"
    assert sess["seed"]["occupation"] == "Pha chế"

    got = await env.a.get(f"/api/creator/sessions/{sid}")
    assert got.status_code == 200 and got.json()["id"] == sid

    patched = await env.a.patch(
        f"/api/creator/sessions/{sid}",
        json={"seed": {"occupation": "Thám tử tư"}, "raw": "Bản nháp thô"},
    )
    assert patched.status_code == 200
    assert patched.json()["target_type"] == "character"
    assert patched.json()["seed"]["occupation"] == "Thám tử tư"
    assert patched.json()["raw"] == "Bản nháp thô"

    # Cross-vault isolation: Vault B always gets 404.
    assert (await env.b.get(f"/api/creator/sessions/{sid}")).status_code == 404
    assert (await env.b.patch(f"/api/creator/sessions/{sid}", json={"raw": "hijack"})).status_code == 404
    assert (await env.b.post(f"/api/creator/sessions/{sid}/message", json={"text": "hi"})).status_code == 404
    assert (await env.b.post(f"/api/creator/sessions/{sid}/generate", json={})).status_code == 404
    assert (await env.b.post(f"/api/creator/sessions/{sid}/save", json={"visibility": "private"})).status_code == 404
    assert (await env.a.get("/api/creator/sessions/not-a-uuid")).status_code == 404


async def test_interview_message_sse_and_missing_key(env: CreatorEnv) -> None:
    sess = (
        await env.a.post(
            "/api/creator/sessions",
            json={"mode": "chat", "target_type": "character", "seed": {}},
        )
    ).json()
    sid = sess["id"]

    # Missing OpenRouter key gives 400 before saving anything.
    env.set_key_present(False)
    missing_resp = await env.a.post(f"/api/creator/sessions/{sid}/message", json={"text": "Tạo nhân vật Mai"})
    assert missing_resp.status_code == 400
    assert missing_resp.json()["error"]["code"] == "openrouter_key_missing"
    assert (await env.a.get(f"/api/creator/sessions/{sid}")).json()["messages"] == []

    env.set_key_present(True)
    env.llm.add([_sse_reply("Chào bạn! ", "Mai bao nhiêu tuổi?")], {"path": COMPLETIONS, "stream": True})
    resp = await env.a.post(f"/api/creator/sessions/{sid}/message", json={"text": "Tạo nhân vật Mai"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    kinds = [e["type"] for e in events]
    assert kinds == ["delta", "delta", "message", "usage", "done"]
    assert "".join(e["delta"] for e in events if e["type"] == "delta") == "Chào bạn! Mai bao nhiêu tuổi?"
    assert events[2]["message"] == {"role": "assistant", "content": "Chào bạn! Mai bao nhiêu tuổi?"}
    done_session = events[-1]["session"]
    assert done_session["messages"] == [
        {"role": "user", "content": "Tạo nhân vật Mai"},
        {"role": "assistant", "content": "Chào bạn! Mai bao nhiêu tuổi?"},
    ]


async def test_generate_sse_and_save_character_and_world(env: CreatorEnv) -> None:
    # 1) Character full flow: raw -> formatted -> validated -> judged -> usage -> done -> save
    char_sess = (
        await env.a.post(
            "/api/creator/sessions",
            json={"mode": "slots", "target_type": "character", "seed": {"occupation": "Pha chế"}},
        )
    ).json()
    csid = char_sess["id"]

    env.set_key_present(False)
    no_key_gen = await env.a.post(f"/api/creator/sessions/{csid}/generate", json={})
    assert no_key_gen.status_code == 400 and no_key_gen.json()["error"]["code"] == "openrouter_key_missing"
    env.set_key_present(True)

    card_json = json.dumps(
        {
            "name": "Vy",
            "age": 24,
            "tagline": "Chủ quán cà phê khuya.",
            "personality": "Điềm tĩnh, thích quan sát khách muộn.",
            "goals": "Giữ quán mở qua mùa đông.",
            "greetings": ['*Lau quầy bar.* "Khách muộn à?"'],
            "tags": ["slice"],
        },
        ensure_ascii=False,
    )
    env.llm.add([_completion("[TÊN]\nQuán cà phê Vy\n[TUỔI]\n24")], {"path": COMPLETIONS, "contains": "Bước 1"})
    env.llm.add([_completion(card_json)], {"path": COMPLETIONS, "contains": "Quán cà phê Vy"})
    env.llm.add([_judge_ok(0.9)], {"path": DECISIONS})

    gen_resp = await env.a.post(f"/api/creator/sessions/{csid}/generate", json={})
    assert gen_resp.status_code == 200
    events = _parse_sse(gen_resp.text)
    kinds = [e["type"] for e in events]
    assert kinds[:4] == ["raw", "formatted", "validated", "judged"]
    assert "usage" in kinds and kinds[-1] == "done"
    assert events[3]["judge_score"]["passed"] is True
    assert events[-1]["session"]["result"]["judge_score"]["score"] == 0.9

    save_resp = await env.a.post(f"/api/creator/sessions/{csid}/save", json={"visibility": "private"})
    assert save_resp.status_code == 201, save_resp.text
    saved_char = save_resp.json()
    assert saved_char["target_type"] == "character"
    assert "world" not in saved_char
    assert saved_char["character"]["judge_score"]["score"] == 0.9

    fetched_char = (await env.a.get(f"/api/characters/{saved_char['item_id']}")).json()["character"]
    assert fetched_char["judge_score"]["passed"] is True

    # 2) World skip_raw flow + save
    world_sess = (
        await env.a.post(
            "/api/creator/sessions",
            json={"mode": "slots", "target_type": "world", "seed": {"tone": "Hoài niệm"}},
        )
    ).json()
    wsid = world_sess["id"]
    world_json = json.dumps(
        {
            "name": "Phố Cũ",
            "rules": "Thế giới đời thường.",
            "locations": [{"id": "pho_cu", "parent_id": None, "level": "area", "name": "Phố Cũ"}],
            "openings": [{"id": "dem_mua", "location_id": "pho_cu", "message": "Đèn vàng hắt xuống mặt đường."}],
            "tags": ["modern"],
        },
        ensure_ascii=False,
    )
    env.llm.add([_completion(world_json)], {"path": COMPLETIONS, "contains": "Bản nháp thế giới có sẵn"})
    wgen = await env.a.post(
        f"/api/creator/sessions/{wsid}/generate",
        json={"skip_raw": True, "raw": "Bản nháp thế giới có sẵn."},
    )
    assert wgen.status_code == 200
    wevents = _parse_sse(wgen.text)
    assert [e["type"] for e in wevents][:3] == ["formatted", "validated", "judged"]
    assert "raw" not in [e["type"] for e in wevents]

    wsave = await env.a.post(f"/api/creator/sessions/{wsid}/save", json={"visibility": "private"})
    assert wsave.status_code == 201, wsave.text
    saved_world = wsave.json()
    assert saved_world["target_type"] == "world"
    assert saved_world["world"]["judge_score"]["passed"] is True
    fetched_world = (await env.a.get(f"/api/worlds/{saved_world['item_id']}")).json()["world"]
    assert fetched_world["judge_score"]["score"] == 0.9


async def test_generate_judge_failure_emits_notice_and_save_guards(env: CreatorEnv) -> None:
    sess = (
        await env.a.post("/api/creator/sessions", json={"mode": "slots", "target_type": "character", "seed": {}})
    ).json()
    sid = sess["id"]

    # Saving before generate fails cleanly.
    not_ready = await env.a.post(f"/api/creator/sessions/{sid}/save", json={"visibility": "private"})
    assert not_ready.status_code == 422 and not_ready.json()["error"]["code"] == "creator_not_generated"

    # Card without age + minor NSFW test.
    minor_nsfw = json.dumps(
        {
            "name": "Hân",
            "age": 16,
            "personality": "Nghịch ngợm.",
            "tags": ["nsfw"],
        },
        ensure_ascii=False,
    )
    env.llm.add([_completion(minor_nsfw)], {"path": COMPLETIONS, "contains": "Tạo bản nháp"})
    # Make Decisions + fallback fail so card_judge runs via run_non_critical and emits notice.
    env.llm.add([{"status": 500, "json": {"error": {"message": "down"}}}], {"path": DECISIONS})
    env.llm.add(
        [{"status": 500, "json": {"error": {"message": "down"}}}], {"path": COMPLETIONS, "contains": "[CÂU HỎI]"}
    )

    gen = await env.a.post(
        f"/api/creator/sessions/{sid}/generate",
        json={"skip_raw": True, "raw": "Tạo bản nháp Hân 16 tuổi"},
    )
    events = _parse_sse(gen.text)
    kinds = [e["type"] for e in events]
    assert "notice" in kinds
    notice = next(e for e in events if e["type"] == "notice")
    assert notice["code"] == "agent_failed" and notice["agent"] == "card_judge"
    assert events[-1]["type"] == "done"
    assert events[-1]["session"]["result"]["judge_score"] is None

    # Public save of minor + nsfw card is blocked by safety rule.
    blocked = await env.a.post(f"/api/creator/sessions/{sid}/save", json={"visibility": "public"})
    assert blocked.status_code == 422 and blocked.json()["error"]["code"] == "nsfw_minor_public"

    # Missing age fails save validation until age is provided in override data; invalid JSON emits SSE error.
    no_age_sess = (
        await env.a.post("/api/creator/sessions", json={"mode": "slots", "target_type": "character", "seed": {}})
    ).json()
    nsid = no_age_sess["id"]
    env.llm.add(
        [_completion(json.dumps({"name": "Không Tuổi", "age": None}, ensure_ascii=False))],
        {"path": COMPLETIONS, "contains": "Không Tuổi draft"},
    )
    env.llm.add([_judge_ok(0.75)], {"path": DECISIONS})
    no_age_gen = await env.a.post(
        f"/api/creator/sessions/{nsid}/generate",
        json={"skip_raw": True, "raw": "Không Tuổi draft"},
    )
    assert no_age_gen.status_code == 200
    no_age_events = _parse_sse(no_age_gen.text)
    assert any(e["type"] == "validated" and e["warnings"][0]["code"] == "age_missing" for e in no_age_events)

    missing_age_save = await env.a.post(f"/api/creator/sessions/{nsid}/save", json={"visibility": "private"})
    assert missing_age_save.status_code == 422 and missing_age_save.json()["error"]["code"] == "validation_error"

    fixed_data = no_age_events[-1]["session"]["result"]["data"]
    fixed_data["age"] = 21
    ok_save = await env.a.post(
        f"/api/creator/sessions/{nsid}/save",
        json={"visibility": "private", "data": fixed_data},
    )
    assert ok_save.status_code == 201 and ok_save.json()["character"]["needs_age"] is False

    bad_sess = (
        await env.a.post("/api/creator/sessions", json={"mode": "slots", "target_type": "character", "seed": {}})
    ).json()
    env.llm.add([_completion("không phải json")], {"path": COMPLETIONS, "contains": "Hỏng cú pháp"})
    bad_gen = await env.a.post(
        f"/api/creator/sessions/{bad_sess['id']}/generate",
        json={"skip_raw": True, "raw": "Hỏng cú pháp"},
    )
    assert bad_gen.status_code == 200
    bad_events = _parse_sse(bad_gen.text)
    assert bad_events == [{"type": "error", "code": "llm_bad_response"}]


async def test_library_judge_endpoints_and_isolation(env: CreatorEnv) -> None:
    char_res = await env.a.post(
        "/api/characters",
        json={
            "data": {"format": "vietrp-card", "spec_version": "1.0", "name": "Lan", "age": 22},
            "visibility": "public",
        },
    )
    assert char_res.status_code == 201
    char_id = char_res.json()["character"]["id"]

    world_res = await env.a.post(
        "/api/worlds",
        json={
            "data": {
                "format": "vietrp-world",
                "spec_version": "1.0",
                "name": "Hà Nội",
                "locations": [{"id": "ho_guom", "level": "place", "name": "Hồ Gươm"}],
            },
            "visibility": "public",
        },
    )
    assert world_res.status_code == 201
    world_id = world_res.json()["world"]["id"]

    # Missing OpenRouter key returns 400.
    env.set_key_present(False)
    assert (await env.a.post(f"/api/characters/{char_id}/judge")).status_code == 400
    assert (await env.a.post(f"/api/worlds/{world_id}/judge")).status_code == 400
    env.set_key_present(True)

    # Cross-vault isolation: Vault B gets 404 even though items are public (judge requires ownership).
    assert (await env.b.post(f"/api/characters/{char_id}/judge")).status_code == 404
    assert (await env.b.post(f"/api/worlds/{world_id}/judge")).status_code == 404

    env.llm.add([_judge_ok(0.84)], {"path": DECISIONS})
    c_judged = await env.a.post(f"/api/characters/{char_id}/judge")
    assert c_judged.status_code == 200
    assert c_judged.json()["character"]["judge_score"]["score"] == 0.84
    assert (await env.a.get(f"/api/characters/{char_id}")).json()["character"]["judge_score"]["passed"] is True

    w_judged = await env.a.post(f"/api/worlds/{world_id}/judge")
    assert w_judged.status_code == 200
    assert w_judged.json()["world"]["judge_score"]["score"] == 0.84
    assert (await env.a.get(f"/api/worlds/{world_id}")).json()["world"]["judge_score"]["passed"] is True

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=env.app), base_url="http://test") as anon:
        assert (await anon.post(f"/api/characters/{char_id}/judge")).status_code == 401
        assert (await anon.post(f"/api/worlds/{world_id}/judge")).status_code == 401
        assert (
            await anon.post("/api/creator/sessions", json={"mode": "slots", "target_type": "character", "seed": {}})
        ).status_code == 401


def test_creator_schemas_export_and_contain_no_secret_fields(tmp_path: Any) -> None:
    from pathlib import Path

    from app.formats.export_schema import SCHEMAS, export_schemas
    from app.schemas import creator as creator_schemas

    written = export_schemas(Path(tmp_path))
    names = {p.name for p in written}
    assert {
        "card-judge-result.schema.json",
        "creator-events.schema.json",
        "creator-generate-in.schema.json",
        "creator-message-in.schema.json",
        "creator-pools-out.schema.json",
        "creator-save-in.schema.json",
        "creator-save-out.schema.json",
        "creator-session-create.schema.json",
        "creator-session-out.schema.json",
        "creator-session-update.schema.json",
    } <= names
    assert names == set(SCHEMAS)

    forbidden = ("api_key", "apikey", "secret", "passphrase", "password", "kek", "dek", "authorization", "bearer")
    for obj in vars(creator_schemas).values():
        fields = getattr(obj, "model_fields", None)
        if isinstance(fields, dict):
            bad = [f for f in fields if any(w in f.lower() for w in forbidden)]
            assert not bad, f"{obj}: {bad}"
