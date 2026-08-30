"""POST /events/{id}/archive|reactivate — confirmation + audit, no hard delete (E03-11)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent

_ALL = [
    "events.create",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.archive",
    "events.reactivate",
]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "archive-test-secret-at-least-32-bytes-okay!!"
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


async def _opened_event(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/v1/events", json={"title": "Fahrgastnotruf B2", "priority": "high"}, headers=_cmd()
    )
    eid = r.json()["id"]
    for verb, ver in (("accept", 1), ("acknowledge", 2), ("open", 3)):
        rr = await client.post(f"/api/v1/events/{eid}/{verb}", headers=_cmd(version=ver))
        assert rr.status_code == 200, rr.text
    return eid  # now status "opened", version 4


async def _reactivate(
    client: httpx.AsyncClient, eid: str, *, version: int, reason: str = "Nachfrage BPol"
) -> httpx.Response:
    """The two-step E20-05 flow: fetch an intent token, then reactivate."""
    intent = await client.post(f"/api/v1/events/{eid}/reactivation-intent")
    assert intent.status_code == 200, intent.text
    return await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": reason, "token": intent.json()["token"]},
        headers=_cmd(version=version),
    )


async def _count(s: AsyncSession, action: str) -> int:
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def _domain_types(s: AsyncSession, eid: str) -> list[str]:
    return [
        r.event_type
        for r in (
            await s.execute(select(DomainEvent).where(DomainEvent.aggregate_id == eid))
        ).scalars()
    ]


async def test_archive_then_reactivate_with_confirm(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl", _ALL)
    await _login(client, "sl")
    eid = await _opened_event(client)

    arch = await client.post(
        f"/api/v1/events/{eid}/archive", json={"reason": "Feierabend"}, headers=_cmd(version=4)
    )
    assert arch.status_code == 200 and arch.json()["status"] == "archived"
    assert await _count(s, "EVENT_ARCHIVED") == 1

    re = await _reactivate(client, eid, version=5)
    assert re.status_code == 200 and re.json()["status"] == "opened"
    assert re.json()["version"] == 6
    assert await _count(s, "EVENT_REACTIVATED") == 1
    assert await _domain_types(s, eid) == [
        "EVENT_CREATED",
        "EVENT_ACCEPTED",
        "EVENT_ACKNOWLEDGED",
        "EVENT_OPENED",
        "EVENT_ARCHIVED",
        "EVENT_REACTIVATED",
    ]


async def test_reactivate_without_confirm_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl2", _ALL)
    await _login(client, "sl2")
    eid = await _opened_event(client)
    await client.post(f"/api/v1/events/{eid}/archive", headers=_cmd(version=4))
    token = (await client.post(f"/api/v1/events/{eid}/reactivation-intent")).json()["token"]

    r = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": False, "reason": "x", "token": token},
        headers=_cmd(version=5),
    )
    assert r.status_code == 422
    assert await _count(s, "EVENT_REACTIVATED") == 0


async def test_reactivate_requires_reason(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl3", _ALL)
    await _login(client, "sl3")
    eid = await _opened_event(client)
    await client.post(f"/api/v1/events/{eid}/archive", headers=_cmd(version=4))
    token = (await client.post(f"/api/v1/events/{eid}/reactivation-intent")).json()["token"]

    r = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "token": token},
        headers=_cmd(version=5),
    )
    assert r.status_code == 422


async def test_archive_from_wrong_state_conflicts(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl4", _ALL)
    await _login(client, "sl4")
    r = await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    eid = r.json()["id"]

    bad = await client.post(f"/api/v1/events/{eid}/archive", headers=_cmd(version=1))
    assert bad.status_code == 409


async def test_archive_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl5", _ALL)
    await _login(client, "sl5")
    eid = await _opened_event(client)

    cid = uuid.uuid4()
    first = await client.post(f"/api/v1/events/{eid}/archive", headers=_cmd(cid, version=4))
    second = await client.post(f"/api/v1/events/{eid}/archive", headers=_cmd(cid, version=4))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await _count(s, "EVENT_ARCHIVED") == 1


async def test_archive_requires_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl6", ["events.create"])
    await _login(client, "sl6")
    r = await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    eid = r.json()["id"]
    bad = await client.post(f"/api/v1/events/{eid}/archive", headers=_cmd(version=1))
    assert bad.status_code == 403


def test_no_delete_endpoint_exists_for_events() -> None:
    from bbz_core.app import create_app

    offenders = [
        route.path
        for route in create_app().routes
        if isinstance(route, APIRoute)
        and route.path.startswith("/api/v1/events")
        and "DELETE" in route.methods
    ]
    assert offenders == [], f"events must never expose a hard-delete: {offenders}"
