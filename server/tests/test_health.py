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


@pytest.fixture(autouse=True)
def _cluster_check(monkeypatch: pytest.MonkeyPatch) -> Callable[[bool, str], None]:
    """The cluster readiness probe defaults to 'ready' (no local Patroni)."""
    state = {"ok": True, "detail": "patroni not configured (single node)"}

    async def fake_local_node_ready() -> tuple[bool, str]:
        return state["ok"], state["detail"]

    monkeypatch.setattr(health_mod, "local_node_ready", fake_local_node_ready)

    def set_state(ok: bool, detail: str) -> None:
        state["ok"], state["detail"] = ok, detail

    return set_state


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
    body = r.json()
    assert body["status"] == "ready"
    assert {c["name"] for c in body["checks"]} == {"database", "cluster"}


async def test_ready_is_503_while_the_node_is_rejoining(
    client: httpx.AsyncClient,
    _db_check: Callable[[bool], None],
    _cluster_check: Callable[[bool, str], None],
) -> None:
    _db_check(True)  # DB fine ...
    _cluster_check(False, "patroni not ready (readiness 503) — rejoin/replay in progress")
    r = await client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert any(c["name"] == "cluster" and c["ok"] is False for c in body["checks"])


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
