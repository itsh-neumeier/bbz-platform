"""HA metrics endpoint + the live stream-connection gauge (E06-13)."""

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


async def test_metrics_expose_the_ha_gauges(env: tuple) -> None:
    client, s = env
    await _make_user(s, "obs", ["system.cluster.view", "events.create"])
    await _login(client, "obs")

    r = await client.get("/api/v1/system/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    body = r.text
    for name in (
        "bbz_cluster_dcs_healthy",
        "bbz_cluster_quorum",
        "bbz_event_seq_head",
        "bbz_outbox_pending",
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
