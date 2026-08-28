"""Async database engine + readiness probe.

No ORM models are defined in the foundation phase. ``check_database`` is used by
``/health/ready`` so a node that cannot reach PostgreSQL never advertises itself
as ready for traffic (MASTER_PROMPT §4).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bbz_core.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    s = get_settings()
    return create_async_engine(
        s.database_url,
        pool_size=s.database_pool_size,
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


async def check_database() -> tuple[bool, str | None]:
    """Return (ok, detail). Never raises."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, None
    except (SQLAlchemyError, OSError) as exc:  # pragma: no cover - env dependent
        return False, f"{type(exc).__name__}: {exc}"


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
