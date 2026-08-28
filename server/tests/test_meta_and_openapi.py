from __future__ import annotations

import httpx


async def test_meta_reports_no_capabilities_yet(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["api_version"] == "v1"
    assert body["capabilities"] == []  # foundation phase


async def test_meta_lists_discovered_mock_integrations(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/meta")
    known = r.json()["known_integrations"]
    # The mock scaffolds shipped in this repo must be discoverable and valid.
    for expected in ("coda_video", "monitor_mock", "telephony_mock"):
        assert expected in known


async def test_openapi_is_versioned(client: httpx.AsyncClient) -> None:
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    doc = r.json()
    assert doc["info"]["version"] == "0.0.0"
    assert "/api/v1/meta" in doc["paths"]
    assert "/health/ready" in doc["paths"]
