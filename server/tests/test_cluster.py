"""Real /cluster/status — live values, permission gate, honest degradation (E06-04)."""

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
    os.environ["BBZ_JWT_SECRET"] = "cluster-test-secret-at-least-32-bytes-okok!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    # force the DCS probe to degrade: nothing listens here
    os.environ["BBZ_CLUSTER_DCS_ENDPOINTS"] = '["http://127.0.0.1:1"]'
    os.environ["BBZ_PATRONI_REST_ENDPOINTS"] = "[]"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    for k in ("BBZ_CLUSTER_DCS_ENDPOINTS", "BBZ_PATRONI_REST_ENDPOINTS"):
        os.environ.pop(k, None)
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


async def test_cluster_status_requires_the_view_permission(env: tuple) -> None:
    client, s = env
    assert (await client.get("/cluster/status")).status_code == 401

    await _make_user(s, "nobody", [])
    await _login(client, "nobody")
    assert (await client.get("/cluster/status")).status_code == 403


async def test_cluster_status_degrades_honestly_when_the_dcs_is_gone(env: tuple) -> None:
    client, s = env
    await _make_user(s, "watcher", ["system.cluster.view"])
    await _login(client, "watcher")

    r = await client.get("/cluster/status")
    assert r.status_code == 200  # never a 500 on probe failure
    body = r.json()
    assert body["stub"] is False
    assert body["dcs"] == "etcd"
    assert body["dcs_healthy"] is False
    assert body["quorum"] is None
    assert body["control_leader"] is None and body["leaders"] == {}
    # this node is always represented, with its real local DB role
    me = next(n for n in body["nodes"] if n["node_id"] == "BBZ-TEST")
    assert me["db_role"] in {"primary", "standby", "unknown"}


@pytest.mark.parametrize(
    ("code", "ready"),
    [(None, True), (200, True), (503, False), (500, False), (-1, False)],
)
async def test_local_node_ready_maps_patroni_readiness(
    monkeypatch: pytest.MonkeyPatch, code: int | None, ready: bool
) -> None:
    from bbz_core.infra import cluster_status

    async def fake() -> int | None:
        return code

    monkeypatch.setattr(cluster_status, "_patroni_readiness_status", fake)
    ok, detail = await cluster_status.local_node_ready()
    assert ok is ready
    assert isinstance(detail, str) and detail


async def test_cluster_status_reports_the_highest_event_seq(env: tuple) -> None:
    client, s = env
    await _make_user(s, "w2", ["system.cluster.view", "events.create"])
    await _login(client, "w2")

    before = (await client.get("/cluster/status")).json()["last_event_seq"]
    await client.post(
        "/api/v1/events",
        json={"title": "x", "priority": "low"},
        headers={"X-Command-Id": str(uuid.uuid4())},
    )
    from bbz_core.infra.models.domain_events import DomainEvent

    seq = (await s.execute(select(DomainEvent.event_seq))).scalars().all()
    after = (await client.get("/cluster/status")).json()["last_event_seq"]
    assert after == max(seq)
    assert before is None or before < after
