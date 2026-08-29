"""Login / session events are audited; the read API needs system.audit.view."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "audit-test-secret-at-least-32-bytes-long!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _mk(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
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


async def test_successful_login_writes_audit(env: tuple) -> None:
    client, s = env
    uid = await _mk(s, "auditor", ["system.audit.view"])
    await client.post(
        "/api/v1/auth/login", json={"username": "auditor", "password": "Wolke7-Bahnhof!x"}
    )

    rows = (await client.get("/api/v1/audit")).json()
    actions = [r["action"] for r in rows]
    assert "LOGIN_SUCCEEDED" in actions and "SESSION_STARTED" in actions
    ok = next(r for r in rows if r["action"] == "LOGIN_SUCCEEDED")
    assert ok["actor_user_id"] == str(uid)
    assert ok["node_id"]


async def test_failed_login_is_audited_without_user_link(env: tuple) -> None:
    client, s = env
    await _mk(s, "carol", ["system.audit.view"])
    # a bad attempt for a name that does not exist — must not leak existence
    await client.post("/api/v1/auth/login", json={"username": "ghost", "password": "x"})
    await client.post(
        "/api/v1/auth/login", json={"username": "carol", "password": "Wolke7-Bahnhof!x"}
    )

    rows = (await client.get("/api/v1/audit?action=LOGIN_FAILED")).json()
    assert rows and rows[0]["actor_user_id"] is None
    assert rows[0]["target_id"] == "ghost"


async def test_audit_read_requires_permission(env: tuple) -> None:
    client, s = env
    await _mk(s, "plain", [])
    await client.post(
        "/api/v1/auth/login", json={"username": "plain", "password": "Wolke7-Bahnhof!x"}
    )
    assert (await client.get("/api/v1/audit")).status_code == 403


async def test_logout_writes_session_ended(env: tuple) -> None:
    client, s = env
    await _mk(s, "dan", ["system.audit.view"])
    login = await client.post(
        "/api/v1/auth/login", json={"username": "dan", "password": "Wolke7-Bahnhof!x"}
    )
    csrf = login.json()["csrf_token"]
    await client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf})

    # re-login to be able to read the log
    await client.post(
        "/api/v1/auth/login", json={"username": "dan", "password": "Wolke7-Bahnhof!x"}
    )
    rows = (await client.get("/api/v1/audit?action=SESSION_ENDED")).json()
    assert rows and rows[0]["reason"] == "logout"
