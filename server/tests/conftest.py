from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest

os.environ.setdefault("BBZ_ENVIRONMENT", "ci")
os.environ.setdefault("BBZ_NODE_ID", "BBZ-TEST")
os.environ.setdefault("BBZ_LOG_JSON", "false")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    # Import inside the fixture so env vars above are applied before settings load.
    from bbz_core.app import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
