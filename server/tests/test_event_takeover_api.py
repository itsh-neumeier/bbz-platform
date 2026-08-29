"""POST /api/v1/events/{id}/takeover — presence gate + mandatory audit (E03-10)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import EventAssignment


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "takeover-test-secret-at-least-32-bytes-ok!!"
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
            pid = (
                await s.execute(select(Permission.id).where(Permission.key == key))
            ).scalar_one_or_none()
            if pid is None:
                p = Permission(key=key, area=key.split(".")[0])
                s.add(p)
                await s.flush()
                pid = p.id
            s.add(RolePermission(role_id=role.id, permission_id=pid, scope="global"))
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


def _fresh(client: httpx.AsyncClient) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]


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


async def _event_assigned_to(client: httpx.AsyncClient, owner: uuid.UUID) -> str:
    """Create an event and assign it to ``owner``; return its id (now at version 2)."""
    c = await client.post(
        "/api/v1/events",
        json={"title": "Oberleitungsschaden", "priority": "critical"},
        headers=_cmd(),
    )
    assert c.status_code == 201, c.text
    eid = c.json()["id"]
    a = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(owner)},
        headers=_cmd(version=1),
    )
    assert a.status_code == 200, a.text
    return eid


async def _active_assignee(s: AsyncSession, eid: str) -> uuid.UUID | None:
    return (
        await s.execute(
            select(EventAssignment.user_id).where(
                EventAssignment.event_id == uuid.UUID(eid),
                EventAssignment.active.is_(True),
            )
        )
    ).scalar_one_or_none()


async def test_takeover_when_owner_offline_succeeds_and_audits(env: tuple) -> None:
    client, s = env
    await _make_user(s, "disponent", ["events.create", "events.assign"])
    owner = await _make_user(s, "owner", [])
    taker = await _make_user(s, "taker", ["events.takeover"])

    await _login(client, "disponent")
    eid = await _event_assigned_to(client, owner)

    taker_client = _fresh(client)
    await _login(taker_client, "taker")
    r = await taker_client.post(
        f"/api/v1/events/{eid}/takeover",
        json={"reason": "Kollege nicht erreichbar"},
        headers=_cmd(version=2),
    )
    assert r.status_code == 200, r.text
    assert await _active_assignee(s, eid) == taker

    types = (
        (await s.execute(select(DomainEvent).where(DomainEvent.aggregate_id == eid)))
        .scalars()
        .all()
    )
    assert [t.event_type for t in types] == ["EVENT_CREATED", "EVENT_ASSIGNED", "EVENT_TAKEN_OVER"]

    audit = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action == "EVENT_TAKEN_OVER")))
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].before == {"assignee_id": str(owner)}
    assert audit[0].after == {"assignee_id": str(taker)}
    assert audit[0].reason == "Kollege nicht erreichbar"


async def test_takeover_blocked_when_owner_available(env: tuple) -> None:
    client, s = env
    await _make_user(s, "disp2", ["events.create", "events.assign"])
    owner = await _make_user(s, "owner2", [])
    await _make_user(s, "taker2", ["events.takeover"])

    await _login(client, "disp2")
    eid = await _event_assigned_to(client, owner)

    owner_client = _fresh(client)
    await _login(owner_client, "owner2")
    assert (
        await owner_client.put("/api/v1/presence", json={"state": "available"})
    ).status_code == 200

    taker_client = _fresh(client)
    await _login(taker_client, "taker2")
    r = await taker_client.post(f"/api/v1/events/{eid}/takeover", headers=_cmd(version=2))
    assert r.status_code == 409
    assert r.json()["error"]["details"]["owner_presence"] == "available"
    assert await _active_assignee(s, eid) == owner

    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EVENT_TAKEN_OVER")
        )
    ).scalar_one() == 0


async def test_takeover_when_owner_on_pause_succeeds(env: tuple) -> None:
    client, s = env
    await _make_user(s, "disp3", ["events.create", "events.assign"])
    owner = await _make_user(s, "owner3", [])
    await _make_user(s, "taker3", ["events.takeover"])
    await _login(client, "disp3")
    eid = await _event_assigned_to(client, owner)

    owner_client = _fresh(client)
    await _login(owner_client, "owner3")
    assert (await owner_client.put("/api/v1/presence", json={"state": "pause"})).status_code == 200

    taker_client = _fresh(client)
    await _login(taker_client, "taker3")
    r = await taker_client.post(f"/api/v1/events/{eid}/takeover", headers=_cmd(version=2))
    assert r.status_code == 200


async def test_takeover_without_owner_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "solo", ["events.create", "events.takeover"])
    await _login(client, "solo")
    c = await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    eid = c.json()["id"]

    r = await client.post(f"/api/v1/events/{eid}/takeover", headers=_cmd(version=1))
    assert r.status_code == 422


async def test_takeover_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "disp4", ["events.create", "events.assign"])
    owner = await _make_user(s, "owner4", [])
    await _make_user(s, "taker4", ["events.takeover"])
    await _login(client, "disp4")
    eid = await _event_assigned_to(client, owner)

    taker_client = _fresh(client)
    await _login(taker_client, "taker4")
    cid = uuid.uuid4()
    first = await taker_client.post(f"/api/v1/events/{eid}/takeover", headers=_cmd(cid, version=2))
    second = await taker_client.post(f"/api/v1/events/{eid}/takeover", headers=_cmd(cid, version=2))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EVENT_TAKEN_OVER")
        )
    ).scalar_one() == 1


async def test_takeover_requires_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "disp5", ["events.create", "events.assign"])
    owner = await _make_user(s, "owner5", [])
    await _make_user(s, "nobody", ["events.create"])
    await _login(client, "disp5")
    eid = await _event_assigned_to(client, owner)

    other = _fresh(client)
    await _login(other, "nobody")
    r = await other.post(f"/api/v1/events/{eid}/takeover", headers=_cmd(version=2))
    assert r.status_code == 403
