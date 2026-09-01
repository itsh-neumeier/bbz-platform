"""Prometheus metrics endpoint (E06-13 HA gauges + E22-02 the full §23 set)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "metrics-test-secret-at-least-32-bytes-ok!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_CLUSTER_DCS_ENDPOINTS"] = '["http://127.0.0.1:1"]'  # degrade the probe
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    os.environ.pop("BBZ_CLUSTER_DCS_ENDPOINTS", None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_user(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    if perms:
        role = Role(key=f"r-{username}", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def test_metrics_requires_cluster_view(env: tuple) -> None:
    client, s = env
    assert (await client.get("/api/v1/system/metrics")).status_code == 401
    await _make_user(s, "nobody", ["events.create"])
    await _login(client, "nobody")
    assert (await client.get("/api/v1/system/metrics")).status_code == 403


async def test_metrics_expose_the_full_section_23_set(env: tuple) -> None:
    client, s = env
    await _make_user(s, "obs", ["system.cluster.view", "events.create"])
    await _login(client, "obs")

    r = await client.get("/api/v1/system/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    for name in (
        # E06-13 HA gauges
        "bbz_cluster_dcs_healthy",
        "bbz_cluster_quorum",
        "bbz_event_seq_head",
        "bbz_outbox_pending",
        "bbz_replication_lag_bytes",
        "bbz_stream_connections",
        # E22-02 §23 set
        "bbz_http_request_duration_seconds",
        "bbz_db_pool_connections",
        "bbz_connected_clients",
        "bbz_commands_pending",
        "bbz_call_lines",
        "bbz_calls_active",
        "bbz_integration_health",
    ):
        assert name in body, name
    # the DCS probe was pointed at a dead port
    assert "bbz_cluster_dcs_healthy 0.0" in body


async def test_event_seq_head_gauge_follows_the_log(env: tuple) -> None:
    client, s = env
    await _make_user(s, "obs2", ["system.cluster.view", "events.create"])
    await _login(client, "obs2")

    await client.post(
        "/api/v1/events",
        json={"title": "x", "priority": "low"},
        headers={"X-Command-Id": str(uuid.uuid4())},
    )
    from bbz_core.infra.models.domain_events import DomainEvent

    seq = max((await s.execute(select(DomainEvent.event_seq))).scalars().all())
    body = (await client.get("/api/v1/system/metrics")).text
    line = next(x for x in body.splitlines() if x.startswith("bbz_event_seq_head "))
    assert float(line.split()[1]) == float(seq)


def test_stream_connection_gauge_tracks_inprogress() -> None:
    from bbz_core.infra.metrics import STREAM_CONNECTIONS, stream_connection

    g = STREAM_CONNECTIONS.labels(transport="sse")
    start = g._value.get()
    with stream_connection("sse"):
        assert g._value.get() == start + 1
    assert g._value.get() == start


def _hist_count(body: str, route: str, status: str) -> float:
    want = f'method="GET",route="{route}",status="{status}"'
    prefix = "bbz_http_request_duration_seconds_count{"
    line = next((x for x in body.splitlines() if x.startswith(prefix) and want in x), None)
    return float(line.split()[1]) if line else 0.0


async def test_request_latency_uses_the_route_template_not_the_raw_path(env: tuple) -> None:
    client, s = env
    await _make_user(s, "obs3", ["system.cluster.view", "events.view"])
    await _login(client, "obs3")

    # a path with a uuid path-param — the label must be the template
    missing = uuid.uuid4()
    await client.get(f"/api/v1/events/{missing}")  # 404 from the handler, still routed

    body = (await client.get("/api/v1/system/metrics")).text
    assert _hist_count(body, "/api/v1/events/{event_id}", "404") >= 1.0
    assert str(missing) not in body  # the raw id never becomes a label


async def test_connected_clients_and_pending_commands_track_state(env: tuple) -> None:
    client, s = env
    await _make_user(s, "obs4", ["system.cluster.view"])
    await _login(client, "obs4")  # one active session now

    body = (await client.get("/api/v1/system/metrics")).text
    clients = next(x for x in body.splitlines() if x.startswith("bbz_connected_clients "))
    assert float(clients.split()[1]) >= 1.0

    from bbz_core.infra.models.commands import Command

    s.add(Command(command_id=uuid.uuid4(), endpoint="/x", request_hash="h"))  # result_status NULL
    await s.commit()
    body = (await client.get("/api/v1/system/metrics")).text
    pending = next(x for x in body.splitlines() if x.startswith("bbz_commands_pending "))
    assert float(pending.split()[1]) >= 1.0


async def test_call_line_status_gauges(env: tuple) -> None:
    client, s = env
    await _make_user(s, "obs5", ["system.cluster.view"])
    await _login(client, "obs5")

    from bbz_core.infra.models.telephony import Call, Line

    s.add(Line(provider="mock", external_id="1001", state="in_service"))
    s.add(Call(bbz_call_id="BBZ-C-1", provider="mock", direction="inbound", state="connected"))
    s.add(Call(bbz_call_id="BBZ-C-2", provider="mock", direction="inbound", state="disconnected"))
    await s.commit()

    body = (await client.get("/api/v1/system/metrics")).text
    line = next(x for x in body.splitlines() if 'bbz_call_lines{state="in_service"}' in x)
    assert float(line.split()[1]) == 1.0
    active = next(x for x in body.splitlines() if x.startswith("bbz_calls_active "))
    assert float(active.split()[1]) == 1.0  # the disconnected one does not count


async def test_integration_health_gauge_reflects_a_loaded_provider(env: tuple) -> None:
    client, s = env
    await _make_user(s, "obs6", ["system.cluster.view"])
    await _login(client, "obs6")

    from bbz_core.integrations_host.providers import active_telephony_provider

    await active_telephony_provider()  # loads the mock into the process cache

    body = (await client.get("/api/v1/system/metrics")).text
    row = next(
        x for x in body.splitlines() if x.startswith("bbz_integration_health{") and "telephony" in x
    )
    assert float(row.split()[1]) == 1.0  # the mock reports healthy
