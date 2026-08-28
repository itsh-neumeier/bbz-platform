from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

import bbz_core.api.health as health_mod


@pytest.fixture(autouse=True)
def _db_check(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool], None]:
    """Health tests must be deterministic regardless of whether a PostgreSQL is
    reachable from the test environment (it is in CI, it is not in a bare venv).
    Patch the DB probe; individual tests opt into 'db up' via the returned setter.
    """
    state = {"ok": False, "detail": "test: db probe disabled"}

    async def fake_check_database() -> tuple[bool, str | None]:
        return state["ok"], None if state["ok"] else state["detail"]

    monkeypatch.setattr(health_mod, "check_database", fake_check_database)

    def set_ok(ok: bool) -> None:
        state["ok"] = ok

    return set_ok


async def test_live(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "live"
    assert body["service"] == "bbz-api"


async def test_ready_is_503_when_database_unreachable(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert any(c["name"] == "database" and c["ok"] is False for c in body["checks"])


async def test_ready_is_200_when_database_ok(
    client: httpx.AsyncClient, _db_check: Callable[[bool], None]
) -> None:
    _db_check(True)
    r = await client.get("/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


async def test_details_includes_node_identity(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/details")
    assert r.status_code == 200
    body = r.json()
    assert body["node_id"] == "BBZ-TEST"
    assert body["environment"] == "ci"


async def test_correlation_id_roundtrip(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/live", headers={"x-correlation-id": "abc-123"})
    assert r.headers["x-correlation-id"] == "abc-123"

    r2 = await client.get("/health/live")
    assert r2.headers.get("x-correlation-id")  # server-generated when absent
