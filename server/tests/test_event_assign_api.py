"""POST /api/v1/events/{id}/assign — ownership handover (E03-09)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.events import EventAssignment

_PERMS = ["events.create", "events.accept", "events.assign"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "assign-test-secret-at-least-32-bytes-okay!!"
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
        json={"title": "Personenunfall Gleis 1", "priority": "critical"},
        headers=_cmd(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _active_assignees(s: AsyncSession, event_id: str) -> list[uuid.UUID]:
    return list(
        (
            await s.execute(
                select(EventAssignment.user_id).where(
                    EventAssignment.event_id == uuid.UUID(event_id),
                    EventAssignment.active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )


async def test_assignable_lists_active_users_for_events_assign(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op1", _PERMS)
    await _make_user(s, "op2", ["events.view"])
    await _login(client, "op1")

    r = await client.get("/api/v1/events/assignable")
    assert r.status_code == 200, r.text
    names = {u["display_name"] for u in r.json()["users"]}
    assert {"Op1", "Op2"} <= names


async def test_assignable_needs_events_assign(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["events.view"])
    await _login(client, "viewer")
    assert (await client.get("/api/v1/events/assignable")).status_code == 403


async def test_assign_and_reassign_keep_one_active(env: tuple) -> None:
    client, s = env
    await _make_user(s, "disponent", _PERMS)
    u2 = await _make_user(s, "kollege", [])
    u3 = await _make_user(s, "kollegin", [])
    await _login(client, "disponent")
    eid = await _create(client)

    r1 = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(u2)},
        headers=_cmd(version=1),
    )
    assert r1.status_code == 200, r1.text
    assert await _active_assignees(s, eid) == [u2]

    r2 = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(u3)},
        headers=_cmd(version=2),
    )
    assert r2.status_code == 200
    assert await _active_assignees(s, eid) == [u3]

    total = (
        await s.execute(
            select(func.count())
            .select_from(EventAssignment)
            .where(EventAssignment.event_id == uuid.UUID(eid))
        )
    ).scalar_one()
    assert total == 2  # one active, one retired


async def test_assign_unknown_user_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "d2", _PERMS)
    await _login(client, "d2")
    eid = await _create(client)

    r = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(uuid.uuid4())},
        headers=_cmd(version=1),
    )
    assert r.status_code == 422
    assert await _active_assignees(s, eid) == []


async def test_self_assignment_allowed(env: tuple) -> None:
    client, s = env
    me = await _make_user(s, "d3", _PERMS)
    await _login(client, "d3")
    eid = await _create(client)

    r = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(me)},
        headers=_cmd(version=1),
    )
    assert r.status_code == 200
    assert await _active_assignees(s, eid) == [me]


async def test_assign_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "d4", _PERMS)
    u2 = await _make_user(s, "k4", [])
    await _login(client, "d4")
    eid = await _create(client)

    cid = uuid.uuid4()
    h = {"target_user_id": str(u2)}
    first = await client.post(f"/api/v1/events/{eid}/assign", json=h, headers=_cmd(cid, version=1))
    second = await client.post(f"/api/v1/events/{eid}/assign", json=h, headers=_cmd(cid, version=1))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await _active_assignees(s, eid) == [u2]


async def test_assign_requires_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "d5", ["events.create"])
    u2 = await _make_user(s, "k5", [])
    await _login(client, "d5")
    eid = await _create(client)

    r = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(u2)},
        headers=_cmd(version=1),
    )
    assert r.status_code == 403
