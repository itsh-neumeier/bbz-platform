"""GET /api/v1/events/priority-alert — topbar warning (E03-15)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

_PERMS = ["events.create", "events.accept", "events.view"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "alert-test-secret-at-least-32-bytes-okayy!!"
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


async def _create(client: httpx.AsyncClient, title: str, priority: str) -> str:
    r = await client.post(
        "/api/v1/events",
        json={"title": title, "priority": priority},
        headers={"X-Command-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_alert_toggles_with_accept(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _PERMS)
    await _login(client, "op")

    assert (await client.get("/api/v1/events/priority-alert")).json() == {
        "active": False,
        "events": [],
    }

    await _create(client, "Kleinkram", "low")
    assert (await client.get("/api/v1/events/priority-alert")).json()["active"] is False

    eid = await _create(client, "Brand Bahnsteig", "critical")
    alert = (await client.get("/api/v1/events/priority-alert")).json()
    assert alert["active"] is True
    assert [e["id"] for e in alert["events"]] == [eid]
    assert alert["events"][0]["priority"] == "critical"

    r = await client.post(
        f"/api/v1/events/{eid}/accept",
        headers={"X-Command-Id": str(uuid.uuid4()), "X-Expected-Version": "1"},
    )
    assert r.status_code == 200
    assert (await client.get("/api/v1/events/priority-alert")).json()["active"] is False


async def test_alert_sorts_critical_before_high(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _PERMS)
    await _login(client, "op2")
    await _create(client, "hoch", "high")
    crit = await _create(client, "kritisch", "critical")

    alert = (await client.get("/api/v1/events/priority-alert")).json()
    assert alert["events"][0]["id"] == crit


async def test_alert_requires_events_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", ["events.create"])
    await _login(client, "op3")
    assert (await client.get("/api/v1/events/priority-alert")).status_code == 403
