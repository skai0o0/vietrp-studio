from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import Base

TEST_DATABASE_URL = os.environ.get("VIETRP_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="VIETRP_TEST_DATABASE_URL is not set")

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


async def _tables(url: str) -> set[str]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = current_schema()")
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


async def _reset_schema(url: str) -> None:
    """Drop everything other Postgres tests left behind via `Base.metadata.create_all`."""
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
    finally:
        await engine.dispose()


def test_upgrade_head_then_downgrade_base() -> None:
    assert TEST_DATABASE_URL is not None
    config = _alembic_config(TEST_DATABASE_URL)
    expected = set(Base.metadata.tables)
    asyncio.run(_reset_schema(TEST_DATABASE_URL))

    command.upgrade(config, "head")
    try:
        assert expected <= asyncio.run(_tables(TEST_DATABASE_URL))
    finally:
        command.downgrade(config, "base")

    assert not (expected & asyncio.run(_tables(TEST_DATABASE_URL)))
