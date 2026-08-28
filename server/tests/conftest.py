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

    for fn in (settings_mod.get_settings, db_mod.get_engine, db_mod.get_sessionmaker):
        fn.cache_clear()
    yield
    for fn in (settings_mod.get_settings, db_mod.get_engine, db_mod.get_sessionmaker):
        fn.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    from bbz_core.app import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
