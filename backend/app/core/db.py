"""Async engine and session factory. Engine creation is lazy so importing the app needs no database."""

from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    # pool_pre_ping survives Postgres restarts on a long-running home server.
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False keeps ORM objects readable after services commit.
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """One session per request. Services own the commit; anything uncommitted is rolled back on exit."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
        get_sessionmaker.cache_clear()
        get_engine.cache_clear()
