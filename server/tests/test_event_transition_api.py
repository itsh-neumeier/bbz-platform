"""POST /events/{id}/accept|acknowledge|open — order, concurrency, idempotency (E03-07)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.domain_events import DomainEvent

_ALL = ["events.create", "events.accept", "events.acknowledge", "events.open"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "trans-test-secret-at-least-32-bytes-okay!!"
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


def _cmd(command_id: uuid.UUID | None = None, *, version: int | None = None) -> dict[str, str]:
    h = {"X-Command-Id": str(command_id or uuid.uuid4())}
    if version is not None:
        h["X-Expected-Version"] = str(version)
    return h


async def _create(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/v1/events",
        json={"title": "Bahnsteigsperrung 3", "priority": "high"},
        headers=_cmd(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _types(s: AsyncSession, event_id: str) -> list[str]:
    rows = (
        (await s.execute(select(DomainEvent).where(DomainEvent.aggregate_id == event_id)))
        .scalars()
        .all()
    )
    return [r.event_type for r in rows]


async def test_accept_acknowledge_open_happy_path(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _ALL)
    await _login(client, "op")
    eid = await _create(client)

    r1 = await client.post(f"/api/v1/events/{eid}/accept", headers=_cmd(version=1))
    assert r1.status_code == 200 and r1.json()["status"] == "accepted"
    assert r1.json()["version"] == 2

    r2 = await client.post(f"/api/v1/events/{eid}/acknowledge", headers=_cmd(version=2))
    assert r2.json()["status"] == "acknowledged" and r2.json()["version"] == 3

    r3 = await client.post(f"/api/v1/events/{eid}/open", headers=_cmd(version=3))
    assert r3.json()["status"] == "opened" and r3.json()["version"] == 4

    assert await _types(s, eid) == [
        "EVENT_CREATED",
        "EVENT_ACCEPTED",
        "EVENT_ACKNOWLEDGED",
        "EVENT_OPENED",
    ]


async def test_wrong_order_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _ALL)
    await _login(client, "op2")
    eid = await _create(client)

    r = await client.post(f"/api/v1/events/{eid}/open", headers=_cmd(version=1))
    assert r.status_code == 409
    assert await _types(s, eid) == ["EVENT_CREATED"]


async def test_stale_version_conflicts_with_details(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", _ALL)
    await _login(client, "op3")
    eid = await _create(client)
    await client.post(f"/api/v1/events/{eid}/accept", headers=_cmd(version=1))

    r = await client.post(f"/api/v1/events/{eid}/acknowledge", headers=_cmd(version=1))
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "conflict"
    assert err["details"]["expected_version"] == 1


async def test_missing_expected_version_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4", _ALL)
    await _login(client, "op4")
    eid = await _create(client)

    r = await client.post(f"/api/v1/events/{eid}/accept", headers=_cmd())
    assert r.status_code == 422


async def test_duplicate_transition_command_replays(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5", _ALL)
    await _login(client, "op5")
    eid = await _create(client)

    cid = uuid.uuid4()
    first = await client.post(f"/api/v1/events/{eid}/accept", headers=_cmd(cid, version=1))
    second = await client.post(f"/api/v1/events/{eid}/accept", headers=_cmd(cid, version=1))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await _types(s, eid) == ["EVENT_CREATED", "EVENT_ACCEPTED"]


async def test_transition_requires_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "creator", ["events.create"])
    await _login(client, "creator")
    eid = await _create(client)

    r = await client.post(f"/api/v1/events/{eid}/accept", headers=_cmd(version=1))
    assert r.status_code == 403
