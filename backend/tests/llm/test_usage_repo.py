from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.llm.usage import SqlUsageRecorder, Usage
from app.repositories import usage_repo

pytestmark = pytest.mark.skipif(
    not os.environ.get("VIETRP_TEST_DATABASE_URL"), reason="VIETRP_TEST_DATABASE_URL is not set"
)


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(os.environ["VIETRP_TEST_DATABASE_URL"])
    yield eng
    await eng.dispose()


async def test_sql_recorder_inserts_scoped_rows(engine: AsyncEngine) -> None:
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    vault_a, vault_b = uuid.uuid4(), uuid.uuid4()
    async with sessionmaker() as session:
        for vault_id in (vault_a, vault_b):
            await session.execute(
                text(
                    "INSERT INTO vaults (id, lookup_hash, kdf_salt, wrapped_dek, display_name) "
                    "VALUES (:id, :lookup, :salt, :dek, 'test')"
                ),
                {"id": vault_id, "lookup": uuid.uuid4().bytes, "salt": b"s", "dek": b"d"},
            )
        await session.commit()
    try:
        recorder = SqlUsageRecorder(sessionmaker)
        await recorder.record(
            vault_a,
            None,
            "writer",
            "m/x",
            Usage(prompt_tokens=10, completion_tokens=5, reasoning_tokens=2, cost=0.00123),
        )
        async with sessionmaker() as session:
            rows_a = await usage_repo.list_recent(session, vault_id=vault_a, limit=10)
            rows_b = await usage_repo.list_recent(session, vault_id=vault_b, limit=10)
        assert len(rows_a) == 1 and rows_b == []
        assert (rows_a[0].agent, rows_a[0].prompt_tokens, rows_a[0].reasoning_tokens) == ("writer", 10, 2)
        assert float(rows_a[0].cost or 0) == pytest.approx(0.00123)
    finally:
        async with sessionmaker() as session:
            await session.execute(text("DELETE FROM vaults WHERE id IN (:a, :b)"), {"a": vault_a, "b": vault_b})
            await session.commit()
