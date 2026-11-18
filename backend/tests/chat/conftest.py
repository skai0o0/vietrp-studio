from __future__ import annotations

import json
import os
import secrets
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.agents.base import LLMGateway
from app.core.config import Settings, get_settings
from app.core.db import get_session
from app.core.deps import GatewayFactory, SessionStoreDep, SettingsDep, get_gateway_factory
from app.core.sessions import VaultSession
from app.llm.config import LLMConfig
from app.llm.deps import build_llm_services
from app.llm.fake import RecordedLLM
from app.main import create_app
from app.models import Base
from app.models.vault import Vault
from app.repositories.chats_repo import SqlChatRepository
from app.repositories.messages_repo import SqlMessageRepository
from app.repositories.presets_repo import SqlPresetRepository
from app.services.asset_service import get_asset_repo
from app.services.chat_service import ChatRepos, UnitOfWork, get_unit_of_work
from app.services.library_service import get_repos
from app.services.turn_service import get_key_check
from app.services.vault_service import VaultService, get_vault_service
from tests.chat.fakes import ChatStore, fake_unit_of_work
from tests.conftest import make_settings
from tests.library.fakes import FakeStore, make_fake_repos
from tests.llm.helpers import FAKE_KEY, FakeRecorder
from tests.vault.conftest import FAST_ARGON2
from tests.vault.fakes import FakeSecretRepository, FakeVaultRepository

TEST_DATABASE_URL = os.environ.get("VIETRP_TEST_DATABASE_URL")


@dataclass
class ChatEnv:
    app: FastAPI
    a: httpx.AsyncClient
    b: httpx.AsyncClient
    llm: RecordedLLM
    recorder: FakeRecorder
    # Replace the LLM transport (e.g. with a gated one) after construction.
    set_transport: Callable[[httpx.AsyncBaseTransport], None]
    ids: dict[str, str] = field(default_factory=dict)


async def _new_vault(client: httpx.AsyncClient, name: str) -> None:
    passphrase = f"chat test {secrets.token_hex(8)} passphrase"
    response = await client.post("/api/vault/create", json={"passphrase": passphrase, "display_name": name})
    assert response.status_code == 201, response.text


def _wire(
    app: FastAPI, settings: Settings
) -> tuple[RecordedLLM, FakeRecorder, Callable[[httpx.AsyncBaseTransport], None]]:
    llm = RecordedLLM.from_dir(names=["wiring_models.json"])
    recorder = FakeRecorder()
    cfg = LLMConfig(backoff_base_seconds=0.0, max_retries=1)
    app.state.llm_services = build_llm_services(settings, transport=llm.transport(), cfg=cfg)

    def set_transport(transport: httpx.AsyncBaseTransport) -> None:
        app.state.llm_services = build_llm_services(settings, transport=transport, cfg=cfg)

    def gateway_factory() -> GatewayFactory:
        def build(vault_session: VaultSession, chat_id: uuid.UUID | None) -> LLMGateway:
            async def key() -> str:
                return FAKE_KEY

            return LLMGateway(
                app.state.llm_services, vault_id=vault_session.vault_id, chat_id=chat_id, api_key=key, recorder=recorder
            )

        return build

    async def no_key_check(_session: VaultSession) -> None:
        return None

    app.dependency_overrides[get_gateway_factory] = gateway_factory
    app.dependency_overrides[get_key_check] = lambda: no_key_check
    return llm, recorder, set_transport


def _settings() -> Settings:
    return make_settings(**FAST_ARGON2, unlock_rate_limit_attempts=10_000, sse_ping_interval_seconds=15)


async def _clients(app: FastAPI, tag: str) -> AsyncIterator[tuple[httpx.AsyncClient, httpx.AsyncClient]]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with (
        httpx.AsyncClient(transport=transport, base_url="http://test") as a,
        httpx.AsyncClient(transport=transport, base_url="http://test") as b,
    ):
        await _new_vault(a, f"Alice {tag}")
        await _new_vault(b, f"Bob {tag}")
        yield a, b


async def _fake_env() -> AsyncIterator[ChatEnv]:
    settings = _settings()
    app = create_app(settings)
    vaults = FakeVaultRepository()
    library = make_fake_repos(FakeStore(vaults))

    def vault_service(session_store: SessionStoreDep, current: SettingsDep) -> VaultService:
        return VaultService(vaults, FakeSecretRepository(), session_store, current)

    uow = fake_unit_of_work(ChatStore(), library)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_vault_service] = vault_service
    app.dependency_overrides[get_repos] = lambda: library
    app.dependency_overrides[get_asset_repo] = lambda: library.assets
    app.dependency_overrides[get_unit_of_work] = lambda: uow
    llm, recorder, set_transport = _wire(app, settings)
    async for a, b in _clients(app, "fake"):
        yield ChatEnv(app, a, b, llm, recorder, set_transport)


async def _pg_env() -> AsyncIterator[ChatEnv]:
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
    async def begin() -> AsyncIterator[ChatRepos]:
        async with sessionmaker() as db:
            yield ChatRepos(
                SqlChatRepository(db),
                SqlMessageRepository(db),
                SqlPresetRepository(db),
                get_repos(db),
                db.commit,
            )

    uow: UnitOfWork = begin
    app.dependency_overrides[get_session] = db_session
    app.dependency_overrides[get_unit_of_work] = lambda: uow
    llm, recorder, set_transport = _wire(app, settings)
    tag = secrets.token_hex(4)
    try:
        async for a, b in _clients(app, tag):
            yield ChatEnv(app, a, b, llm, recorder, set_transport)
    finally:
        async with sessionmaker() as session:
            await session.execute(delete(Vault).where(Vault.display_name.in_([f"Alice {tag}", f"Bob {tag}"])))
            await session.commit()
        await engine.dispose()


@pytest.fixture(params=["fake", "postgres"])
async def env(request: pytest.FixtureRequest) -> AsyncIterator[ChatEnv]:
    if request.param == "postgres" and not TEST_DATABASE_URL:
        pytest.skip("VIETRP_TEST_DATABASE_URL is not set")
    factory = _fake_env if request.param == "fake" else _pg_env
    async for value in factory():
        yield value
        await env_services_close(value)


async def env_services_close(env: ChatEnv) -> None:
    await env.app.state.llm_services.aclose()


# --- helpers for tests ---


def card_data(name: str = "Mai", **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "format": "vietrp-card",
        "spec_version": "1.0",
        "name": name,
        "age": 25,
        "tagline": "",
        "personality": "Điềm tĩnh",
        "greetings": ["Chào {{user}}, hôm nay trời đẹp.", "Lời mở đầu thứ hai"],
        "tags": ["slice"],
    }
    data.update(overrides)
    return data


async def make_character(client: httpx.AsyncClient, **overrides: Any) -> str:
    response = await client.post("/api/characters", json={"data": card_data(**overrides), "visibility": "private"})
    assert response.status_code == 201, response.text
    return str(response.json()["character"]["id"])


async def make_persona(client: httpx.AsyncClient, name: str = "Nam") -> str:
    data = {"format": "vietrp-persona", "spec_version": "1.0", "name": name, "age": 22}
    response = await client.post("/api/personas", json={"data": data})
    assert response.status_code == 201, response.text
    body = response.json()
    return str((body.get("persona") or body)["id"])


async def make_chat(client: httpx.AsyncClient, character_id: str, **body: Any) -> dict[str, Any]:
    response = await client.post("/api/chats", json={"character_id": character_id, **body})
    assert response.status_code == 201, response.text
    result: dict[str, Any] = response.json()
    return result


def parse_sse(text: str) -> list[dict[str, Any]]:
    """The `data:` JSON of every event in an SSE body."""
    events: list[dict[str, Any]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        data = "\n".join(line[5:].strip() for line in block.split("\n") if line.startswith("data:"))
        if data:
            events.append(json.loads(data))
    return events


async def run_turn(client: httpx.AsyncClient, chat_id: str, text: str, **body: Any) -> list[dict[str, Any]]:
    response = await client.post(f"/api/chats/{chat_id}/turn", json={"text": text, **body})
    assert response.status_code == 200, response.text
    return parse_sse(response.text)


# --- LLM scripting ---

DECISIONS = "/api/alpha/decisions"
COMPLETIONS = "/api/v1/chat/completions"


def sse_stream(*parts: str, prompt_tokens: int = 100) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = [{"id": "g", "choices": [{"delta": {"role": "assistant", "content": ""}}]}]
    chunks += [{"id": "g", "choices": [{"delta": {"content": p}, "finish_reason": None}]} for p in parts]
    chunks.append({"id": "g", "choices": [{"delta": {}, "finish_reason": "stop"}]})
    chunks.append({"id": "g", "choices": [], "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": 8}})
    return {"status": 200, "sse": chunks}


def decision(answers: dict[str, Any]) -> dict[str, Any]:
    usage = {"prompt_tokens": 50, "completion_tokens": 4, "cost": 0.0001}
    return {"status": 200, "json": {"model": "microsoft/microsoft-decision-1", "usage": usage, "answers": answers}}


DIRECTOR_PASS = decision(
    {
        "answers_last": {"noul": 0.95},
        "no_new_events": {"noul": 0.05},
        "no_player_voice": {"noul": 0.03},
        "no_assistant_voice": {"noul": 0.02},
        "user_led": {"noul": 0.1},
        "priority": {"score": 1.0},
    }
)


def director_fail(player_voice: float = 0.6) -> dict[str, Any]:
    """Rejected because `no_player_voice` is only `1 - player_voice` satisfied."""
    return decision(
        {
            "answers_last": {"noul": 0.9},
            "no_new_events": {"noul": 0.1},
            "no_player_voice": {"noul": player_voice},
            "no_assistant_voice": {"noul": 0.02},
            "user_led": {"noul": 0.1},
            "priority": {"score": 0.0},
        }
    )


def script_llm(
    llm: RecordedLLM,
    character_id: str,
    *,
    writer: list[dict[str, Any]],
    director: list[dict[str, Any]] | None = None,
) -> None:
    """Orchestrator (dialogue, character), Bond Drafter/Selector, Writer and Director replies for one chat."""
    pair = f"{character_id}:user"
    bond_json = {
        "pairs": {
            pair: [
                {"addressing": "anh - em", "relationship": "bạn cũ", "stance": "thân thiện", "closeness": 2},
                {"addressing": "tôi - cậu", "relationship": "đồng nghiệp", "stance": "lịch sự", "closeness": 1},
            ]
        }
    }
    llm.add(
        [
            {
                "status": 200,
                "json": {
                    "choices": [{"message": {"role": "assistant", "content": json.dumps(bond_json)}}],
                    "usage": {"prompt_tokens": 80, "completion_tokens": 30},
                },
            }
        ],
        {"path": COMPLETIONS, "stream": False, "contains": "Mã cặp"},
        name="bond_drafter",
    )
    llm.add(
        [decision({"bond__0": {"choice": "2", "confidence": 0.7, "probabilities": {"1": 0.3, "2": 0.7}}})],
        {"path": DECISIONS, "contains": "bond__0"},
        name="bond_selector",
    )
    llm.add(
        [
            decision(
                {
                    "turn_type": {"choice": "dialogue", "confidence": 0.9, "probabilities": {"dialogue": 0.9}},
                    "speaker": {"choice": "character", "confidence": 0.9, "probabilities": {"character": 0.9}},
                    "addressee": {"choice": "character", "confidence": 0.9, "probabilities": {"character": 0.9}},
                }
            )
        ],
        {"path": DECISIONS, "contains": "turn_type"},
        name="orchestrator",
    )
    llm.add(director or [DIRECTOR_PASS], {"path": DECISIONS, "contains": "answers_last"}, name="director")
    llm.add(writer, {"path": COMPLETIONS, "stream": True}, name="writer")
