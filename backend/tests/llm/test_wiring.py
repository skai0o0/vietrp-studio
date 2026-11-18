"""LLM wiring: shared services, the gateway's usage accounting, and the RecordedLLM fake."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.agents.base import LLMGateway
from app.llm.chat import ContentDelta, Finish
from app.llm.client import LLMError
from app.llm.config import LLMConfig
from app.llm.decisions import Choice, Noul, Question
from app.llm.deps import LLMServices, build_llm_services
from app.llm.extractions import Field
from app.llm.fake import RecordedLLM, UnmatchedRequest
from app.llm.usage import SqlUsageRecorder, Usage
from app.main import create_app
from app.repositories import usage_repo
from tests.conftest import make_settings
from tests.llm.helpers import FAKE_KEY, FakeRecorder

WRITER_MODEL = "deepseek/deepseek-v4.1-flash-1017"
DECISION_MODEL = "microsoft/microsoft-decision-1"
MESSAGES = [{"role": "user", "content": "Chào"}]
QUESTIONS: dict[str, Question] = {
    "speaker": Choice(criteria={"mai": "Mai", "narrator": "Người dẫn truyện"}, instructions="Ai nói tiếp?"),
    "lore__a": Noul(instructions="Cần thông tin A?"),
}


class KeyCounter:
    """An ApiKeyProvider that counts how often the key is fetched."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> str:
        self.calls += 1
        return FAKE_KEY


def make_gateway(
    llm: RecordedLLM, recorder: FakeRecorder | None = None, key: KeyCounter | None = None
) -> tuple[LLMGateway, LLMServices, FakeRecorder, KeyCounter]:
    recorder = recorder or FakeRecorder()
    key = key or KeyCounter()
    services = build_llm_services(
        make_settings(), transport=llm.transport(), cfg=LLMConfig(backoff_base_seconds=0.0, max_retries=2)
    )
    gateway = LLMGateway(services, vault_id=uuid.uuid4(), chat_id=uuid.uuid4(), api_key=key, recorder=recorder)
    return gateway, services, recorder, key


def recorded(*names: str) -> RecordedLLM:
    return RecordedLLM.from_dir(names=[f"wiring_{n}.json" for n in names])


async def test_stream_replays_chunks_and_records_priced_usage() -> None:
    gateway, services, recorder, key = make_gateway(recorded("models", "chat_stream"))
    try:
        events = [e async for e in gateway.stream("writer", WRITER_MODEL, MESSAGES)]
    finally:
        await services.aclose()
    assert "".join(e.text for e in events if isinstance(e, ContentDelta)) == "Xin chào bạn"
    assert any(isinstance(e, Finish) and e.reason == "stop" for e in events)
    final = events[-1]
    assert isinstance(final, Usage)
    # No provider cost in the fixture: priced from the models fixture (0.2 / 0.8 USD per million tokens).
    assert final.cost == pytest.approx(1000 * 0.0000002 + 500 * 0.0000008)
    assert len(recorder.calls) == 1
    vault_id, chat_id, agent, model, usage = recorder.calls[0]
    assert (vault_id, chat_id, agent, model) == (gateway.vault_id, gateway.chat_id, "writer", WRITER_MODEL)
    assert usage.cost == final.cost and usage.prompt_tokens == 1000
    assert key.calls == 1
    assert services.corrections.factor(WRITER_MODEL) > 1.0  # real prompt tokens fed back
    assert gateway.drain_usage() == [usage] and gateway.drain_usage() == []


async def test_complete_keeps_provider_cost_and_reads_key_per_call() -> None:
    gateway, services, recorder, key = make_gateway(recorded("models", "chat_complete"))
    try:
        messages = [{"role": "user", "content": "Hãy tóm tắt đoạn này."}]
        for _ in range(2):
            text_out, usage = await gateway.complete("archivist", WRITER_MODEL, messages)
    finally:
        await services.aclose()
    assert text_out == "Bản tóm tắt." and usage.cost == 0.0005
    assert key.calls == 2
    assert [c[2] for c in recorder.calls] == ["archivist", "archivist"]


async def test_decide_and_extract_price_and_record() -> None:
    gateway, services, recorder, _ = make_gateway(recorded("models", "decisions", "extractions"))
    try:
        decision = await gateway.decide("orchestrator", DECISION_MODEL, {"scene": "x"}, QUESTIONS)
        extraction = await gateway.extract("state_keeper", DECISION_MODEL, "đoạn", {"time": Field(instructions="Giờ?")})
    finally:
        await services.aclose()
    assert decision.choice("speaker").choice == "mai" and not decision.used_fallback
    assert decision.usage.cost == pytest.approx(400 * 0.000001 + 10 * 0.000002)
    assert extraction.values["time"].value == "Chiều thứ Bảy"
    assert [(c[2], c[3]) for c in recorder.calls] == [
        ("orchestrator", DECISION_MODEL),
        ("state_keeper", DECISION_MODEL),
    ]
    assert all(c[4].cost is not None for c in recorder.calls)


async def test_decisions_fall_back_to_chat_when_alpha_api_is_gone() -> None:
    llm = recorded("models")
    llm.add([{"status": 404, "json": {"error": {"message": "gone"}}}], {"path": "/api/alpha/decisions"})
    content = '{"speaker":{"probabilities":{"mai":3,"narrator":1}},"lore__a":{"p":0.7}}'
    llm.add(
        [
            {
                "status": 200,
                "json": {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"prompt_tokens": 300, "completion_tokens": 40, "cost": 0.0003},
                },
            }
        ],
        {"path": "/api/v1/chat/completions"},
    )
    gateway, services, recorder, _ = make_gateway(llm)
    try:
        result = await gateway.decide("orchestrator", DECISION_MODEL, {"scene": "x"}, QUESTIONS)
    finally:
        await services.aclose()
    assert result.used_fallback and result.choice("speaker").choice == "mai"
    assert len(recorder.calls) == 1  # only the call that was actually billed


async def test_retry_on_429_then_success() -> None:
    llm = recorded("models")
    llm.add(
        [
            {"status": 429, "json": {"error": {"message": "slow down"}}},
            {"status": 200, "json": {"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 1}}},
        ],
        {"path": "/api/v1/chat/completions"},
    )
    gateway, services, recorder, _ = make_gateway(llm)
    try:
        out, _usage = await gateway.complete("writer", WRITER_MODEL, MESSAGES)
    finally:
        await services.aclose()
    assert out == "ok" and len(llm.requests_to("/api/v1/chat/completions")) == 2 and len(recorder.calls) == 1


async def test_secret_never_reaches_usage_events_or_exceptions() -> None:
    llm = recorded("models", "chat_stream", "decisions")
    # An upstream that echoes the Authorization header back in its error body.
    llm.add(
        [{"status": 401, "json": {"error": {"message": f"invalid key {FAKE_KEY}"}}}],
        {"path": "/api/v1/chat/completions", "stream": False},
    )
    gateway, services, recorder, _ = make_gateway(llm)
    try:
        with pytest.raises(LLMError) as raised:
            await gateway.complete("writer", WRITER_MODEL, MESSAGES)
        _ = [e async for e in gateway.stream("writer", WRITER_MODEL, MESSAGES)]
        await gateway.decide("orchestrator", DECISION_MODEL, {}, QUESTIONS)
    finally:
        await services.aclose()
    assert FAKE_KEY not in str(raised.value) and FAKE_KEY not in repr(raised.value)
    assert FAKE_KEY not in repr(recorder.calls) + repr(gateway.collected)
    # The key is sent upstream (that is the point) but only as a header, never in a request body.
    assert all(FAKE_KEY not in r.content.decode() for r in llm.requests if r.content)
    assert any(r.headers.get("authorization") == f"Bearer {FAKE_KEY}" for r in llm.requests)


async def test_fake_rejects_unmatched_requests() -> None:
    gateway, services, _, _ = make_gateway(RecordedLLM())
    try:
        with pytest.raises(UnmatchedRequest):
            await gateway.complete("writer", WRITER_MODEL, MESSAGES)
    finally:
        await services.aclose()


def test_plain_p0_fixtures_are_ignored_by_the_loader() -> None:
    llm = RecordedLLM.from_dir()  # chat_complete.json and friends are raw bodies without the marker
    assert llm.fixture_names and "chat_complete.json" not in llm.fixture_names
    with pytest.raises(ValueError):
        RecordedLLM.from_dir(names=["chat_complete.json"])


async def test_lifespan_builds_and_closes_shared_services() -> None:
    app = create_app(make_settings())
    async with app.router.lifespan_context(app):
        services = app.state.llm_services
        assert isinstance(services, LLMServices)
    assert services.client._http.is_closed


async def test_lifespan_keeps_preset_services() -> None:
    app = create_app(make_settings())
    preset = build_llm_services(make_settings(), transport=RecordedLLM().transport())
    app.state.llm_services = preset
    async with app.router.lifespan_context(app):
        assert app.state.llm_services is preset


# --- database-backed ---

needs_db = pytest.mark.skipif(
    not os.environ.get("VIETRP_TEST_DATABASE_URL"), reason="VIETRP_TEST_DATABASE_URL is not set"
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(os.environ["VIETRP_TEST_DATABASE_URL"])
    yield eng
    await eng.dispose()


@needs_db
async def test_gateway_writes_usage_log_rows_with_cost(engine: AsyncEngine) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    vault_id, chat_id = uuid.uuid4(), uuid.uuid4()
    async with sessionmaker() as session:
        await session.execute(
            text(
                "INSERT INTO vaults (id, lookup_hash, kdf_salt, wrapped_dek, display_name) "
                "VALUES (:id, :lookup, :salt, :dek, 'test')"
            ),
            {"id": vault_id, "lookup": uuid.uuid4().bytes, "salt": b"s", "dek": b"d"},
        )
        await session.execute(
            text("INSERT INTO chats (id, vault_id, mode) VALUES (:id, :vault, 'single')"),
            {"id": chat_id, "vault": vault_id},
        )
        await session.commit()
    try:
        services = build_llm_services(
            make_settings(), transport=recorded("models", "chat_stream", "decisions").transport()
        )
        gateway = LLMGateway(
            services,
            vault_id=vault_id,
            chat_id=chat_id,
            api_key=KeyCounter(),
            recorder=SqlUsageRecorder(sessionmaker),
        )
        try:
            _ = [e async for e in gateway.stream("writer", WRITER_MODEL, MESSAGES)]
            await gateway.decide("orchestrator", DECISION_MODEL, {}, QUESTIONS)
        finally:
            await services.aclose()
        async with sessionmaker() as session:
            rows = await usage_repo.list_recent(session, vault_id=vault_id, limit=10)
            totals = await usage_repo.totals_for_chat(session, vault_id=vault_id, chat_id=chat_id)
            other = await usage_repo.totals_for_chat(session, vault_id=uuid.uuid4(), chat_id=chat_id)
        assert sorted(r.agent for r in rows) == ["orchestrator", "writer"]
        assert all(r.cost is not None and r.cost > 0 for r in rows)
        assert totals.calls == 2 and totals.prompt_tokens == 1400
        assert float(totals.cost) == pytest.approx(0.0006 + 0.00042)
        assert other.calls == 0  # scoped by vault
    finally:
        async with sessionmaker() as session:
            await session.execute(text("DELETE FROM vaults WHERE id = :id"), {"id": vault_id})
            await session.commit()
