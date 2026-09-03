"""GET /events/logbook — the cross-workplace activity feed (MASTER_PROMPT §13.1)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

_PERMS = ["events.create", "events.view", "events.accept", "events.acknowledge"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "logbook-test-secret-at-least-32-bytes-ok!!"
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


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def test_logbook_returns_recent_lifecycle_events_newest_first(env: tuple) -> None:
    client, s = env
    await _make_user(s, "leit", _PERMS)
    await _login(client, "leit")

    a = (
        await client.post(
            "/api/v1/events", json={"title": "BMA Halle 7", "priority": "critical"}, headers=_cmd()
        )
    ).json()["id"]
    b = (
        await client.post(
            "/api/v1/events", json={"title": "Aufzug Gleis 3", "priority": "high"}, headers=_cmd()
        )
    ).json()["id"]
    await client.post(f"/api/v1/events/{a}/accept", headers={**_cmd(), "X-Expected-Version": "1"})

    r = await client.get("/api/v1/events/logbook")
    assert r.status_code == 200
    items = r.json()["items"]

    # newest first, by event_seq
    seqs = [i["event_seq"] for i in items]
    assert seqs == sorted(seqs, reverse=True)

    # the accept is the most recent entry and carries the joined event + actor
    top = items[0]
    assert top["event_type"] == "EVENT_ACCEPTED"
    assert top["event_id"] == a
    assert top["title"] == "BMA Halle 7"
    assert top["priority"] == "critical"
    assert top["status"] == "accepted"
    assert top["actor"] == "Leit"

    # both creations are in the feed
    kinds = {(i["event_id"], i["event_type"]) for i in items}
    assert (a, "EVENT_CREATED") in kinds
    assert (b, "EVENT_CREATED") in kinds


async def test_logbook_respects_limit(env: tuple) -> None:
    client, s = env
    await _make_user(s, "leit2", _PERMS)
    await _login(client, "leit2")
    for n in range(5):
        await client.post(
            "/api/v1/events", json={"title": f"E{n}", "priority": "low"}, headers=_cmd()
        )

    items = (await client.get("/api/v1/events/logbook?limit=3")).json()["items"]
    assert len(items) == 3


async def test_logbook_requires_events_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "noview", ["events.create"])
    await _login(client, "noview")
    assert (await client.get("/api/v1/events/logbook")).status_code == 403
