from __future__ import annotations

import httpx


async def test_live(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/live")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "live"
    assert body["service"] == "bbz-api"


async def test_ready_reports_not_ready_without_database(client: httpx.AsyncClient) -> None:
    # No PostgreSQL in the unit-test environment -> the node must NOT claim readiness.
    r = await client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert any(c["name"] == "database" and c["ok"] is False for c in body["checks"])


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
