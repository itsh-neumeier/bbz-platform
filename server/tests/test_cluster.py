from __future__ import annotations

import httpx


async def test_cluster_status_is_honestly_labelled_stub(client: httpx.AsyncClient) -> None:
    r = await client.get("/cluster/status")
    assert r.status_code == 200
    body = r.json()
    # Phase 0: must advertise that it is NOT authoritative.
    assert body["stub"] is True
    assert body["dcs"] in {"etcd", "consul"}
    assert body["nodes"][0]["node_id"] == "BBZ-TEST"
    assert body["control_leader"] is None
    assert body["last_event_seq"] is None
