from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import httpx
import pytest

import bbz_core.api.health as health_mod


@pytest.fixture(autouse=True)
def _auth_env() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "health-test-secret-at-least-32-bytes-ok!!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


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

    async def fake_dcs_reachable() -> tuple[bool, str | None]:
        return True, "no DCS configured (single node)"

    monkeypatch.setattr(health_mod, "local_node_ready", fake_local_node_ready)
    monkeypatch.setattr(health_mod, "dcs_reachable", fake_dcs_reachable)

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


async def _login_with_cluster_view(client: httpx.AsyncClient, db: object) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    s = db
    assert isinstance(s, AsyncSession)
    u = User(display_name="Ops")
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject="ops")
    s.add(ident)
    await s.flush()
    pw = hash_password("Wolke7-Bahnhof!x")
    s.add(LocalCredential(auth_identity_id=ident.id, password_hash=pw))
    role = Role(key="r-ops", name="Ops")
    s.add(role)
    await s.flush()
    perm = Permission(key="system.cluster.view", area="system")
    s.add(perm)
    await s.flush()
    s.add(RolePermission(role_id=role.id, permission_id=perm.id, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()

    r = await client.post(
        "/api/v1/auth/login", json={"username": "ops", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def test_details_requires_cluster_view(client: httpx.AsyncClient) -> None:
    assert (await client.get("/health/details")).status_code == 401


async def test_details_reports_build_and_a_timed_dependency_matrix(
    client: httpx.AsyncClient, db: object, _db_check: Callable[[bool], None]
) -> None:
    _db_check(True)
    await _login_with_cluster_view(client, db)

    r = await client.get("/health/details")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["node_id"] == "BBZ-TEST"
    assert body["environment"] == "ci"
    assert body["build"]["version"] == body["version"]
    assert body["build"]["revision"] == "unknown" and body["build"]["built_at"] == "unknown"
    names = {c["name"] for c in body["checks"]}
    assert names == {"database", "cluster", "dcs"}
    for c in body["checks"]:
        assert isinstance(c["duration_ms"], (int, float))
    assert next(c for c in body["checks"] if c["name"] == "database")["ok"] is True


async def test_details_reflects_a_failing_dependency(
    client: httpx.AsyncClient, db: object, _db_check: Callable[[bool], None]
) -> None:
    _db_check(False)  # DB probe down
    await _login_with_cluster_view(client, db)

    body = (await client.get("/health/details")).json()
    db_check = next(c for c in body["checks"] if c["name"] == "database")
    assert db_check["ok"] is False
    assert db_check["detail"]  # a reason is surfaced


async def test_correlation_id_roundtrip(client: httpx.AsyncClient) -> None:
    r = await client.get("/health/live", headers={"x-correlation-id": "abc-123"})
    assert r.headers["x-correlation-id"] == "abc-123"

    r2 = await client.get("/health/live")
    assert r2.headers.get("x-correlation-id")  # server-generated when absent
