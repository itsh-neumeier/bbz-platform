from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

os.environ.setdefault("BBZ_ENVIRONMENT", "ci")
os.environ.setdefault("BBZ_NODE_ID", "BBZ-TEST")
os.environ.setdefault("BBZ_LOG_JSON", "false")
# Point tests at a definitely-unreachable database. Tests that need DB behaviour
# patch the probe (see test_health.py); nothing in the unit suite opens a real
# connection, which also avoids asyncpg's event-loop binding across test loops.
os.environ.setdefault("BBZ_DATABASE_URL", "postgresql+asyncpg://x:x@127.0.0.1:1/none")


@pytest.fixture(autouse=True)
def _reset_caches() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.infra import db as db_mod
    from bbz_core.infra.repositories import contact_matching as matching_mod
    from bbz_core.integrations_host import providers as providers_mod

    for fn in (settings_mod.get_settings, db_mod.get_engine, db_mod.get_sessionmaker):
        fn.cache_clear()
    providers_mod.reset_provider_cache()
    matching_mod.clear_matcher_cache()
    yield
    for fn in (settings_mod.get_settings, db_mod.get_engine, db_mod.get_sessionmaker):
        fn.cache_clear()
    providers_mod.reset_provider_cache()
    matching_mod.clear_matcher_cache()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from bbz_core.app import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
async def db() -> AsyncIterator[object]:
    """An ``AsyncSession`` against a real PostgreSQL, or skip.

    CI's backend job provides PostgreSQL and sets ``BBZ_DATABASE_URL``. Locally,
    export ``BBZ_DATABASE_URL`` (e.g. the dev-compose db) to run these.
    """
    from sqlalchemy import text as _sql

    from bbz_core.infra.db import get_engine, get_sessionmaker
    from bbz_core.infra.models import Base

    engine = get_engine()
    try:
        async with engine.connect() as conn:
            await conn.execute(_sql("SELECT 1"))
    except Exception:  # any connection failure here means "no DB in this env"
        pytest.skip("no PostgreSQL available (set BBZ_DATABASE_URL)")

    async with engine.begin() as conn:
        await conn.execute(_sql('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        await conn.execute(_sql('CREATE EXTENSION IF NOT EXISTS "citext"'))
        await conn.execute(_sql('CREATE EXTENSION IF NOT EXISTS "pg_trgm"'))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with get_sessionmaker()() as session:
        yield session

    # Leave a clean DB: the CI backend job runs Alembic after pytest, and it
    # must not collide with tables created here.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.execute(_sql("DROP TABLE IF EXISTS alembic_version"))
    await engine.dispose()
