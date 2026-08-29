"""Presence: self set/get, roster needs users.view, auto-offline without session."""

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
    os.environ["BBZ_JWT_SECRET"] = "presence-test-secret-at-least-32-bytes-ok!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
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


async def test_set_and_read_own_presence(env: tuple) -> None:
    client, s = env
    await _make_user(s, "alice", [])
    await _login(client, "alice")

    assert (await client.get("/api/v1/presence/me")).json()["state"] == "offline"  # stored default
    r = await client.put("/api/v1/presence", json={"state": "available"})
    assert r.status_code == 200 and r.json()["state"] == "available"
    assert (await client.put("/api/v1/presence", json={"state": "banana"})).status_code == 422


async def test_roster_requires_users_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "bob", [])
    await _login(client, "bob")
    assert (await client.get("/api/v1/presence")).status_code == 403


async def test_effective_offline_when_no_live_session(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sichtleiter", ["users.view"])
    carl = await _make_user(s, "carl", [])

    carl_client = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with carl_client:
        await _login(carl_client, "carl")
        await carl_client.put("/api/v1/presence", json={"state": "available"})
        # logout drops carl's session
        csrf = carl_client.cookies.get("bbz_csrf")
        await carl_client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf or ""})

    await _login(client, "sichtleiter")
    roster = {row["user_id"]: row for row in (await client.get("/api/v1/presence")).json()}
    assert roster[str(carl)]["stored_state"] == "available"
    assert roster[str(carl)]["state"] == "offline"  # no live session -> effective offline
