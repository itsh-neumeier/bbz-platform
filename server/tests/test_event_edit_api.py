"""PATCH /api/v1/events/{id} — whitelist, optimistic concurrency, idempotency (E03-08)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.domain_events import DomainEvent

_PERMS = ["events.create", "events.edit"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "edit-test-secret-at-least-32-bytes-okayyy!!"
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
        json={"title": "Aufzug Nord defekt", "priority": "medium"},
        headers=_cmd(),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _updated_events(s: AsyncSession, event_id: str) -> list[DomainEvent]:
    return list(
        (
            await s.execute(
                select(DomainEvent).where(
                    DomainEvent.aggregate_id == event_id,
                    DomainEvent.event_type == "EVENT_UPDATED",
                )
            )
        )
        .scalars()
        .all()
    )


async def test_edit_updates_fields_and_emits_diff(env: tuple) -> None:
    client, s = env
    await _make_user(s, "editor", _PERMS)
    await _login(client, "editor")
    eid = await _create(client)

    r = await client.patch(
        f"/api/v1/events/{eid}",
        json={"title": "Aufzug Nord + Süd defekt", "priority": "high"},
        headers=_cmd(version=1),
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Aufzug Nord + Süd defekt"
    assert r.json()["priority"] == "high"
    assert r.json()["version"] == 2

    evs = await _updated_events(s, eid)
    assert len(evs) == 1
    assert evs[0].payload["changes"]["priority"] == {"from": "medium", "to": "high"}


async def test_edit_stale_version_conflicts(env: tuple) -> None:
    client, s = env
    await _make_user(s, "editor2", _PERMS)
    await _login(client, "editor2")
    eid = await _create(client)
    await client.patch(f"/api/v1/events/{eid}", json={"title": "v2"}, headers=_cmd(version=1))

    r = await client.patch(
        f"/api/v1/events/{eid}", json={"title": "again"}, headers=_cmd(version=1)
    )
    assert r.status_code == 409


async def test_edit_rejects_unknown_field(env: tuple) -> None:
    client, s = env
    await _make_user(s, "editor3", _PERMS)
    await _login(client, "editor3")
    eid = await _create(client)

    r = await client.patch(
        f"/api/v1/events/{eid}", json={"status": "opened"}, headers=_cmd(version=1)
    )
    assert r.status_code == 422


async def test_edit_empty_body_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "editor4", _PERMS)
    await _login(client, "editor4")
    eid = await _create(client)

    r = await client.patch(f"/api/v1/events/{eid}", json={}, headers=_cmd(version=1))
    assert r.status_code == 422


async def test_edit_requires_expected_version(env: tuple) -> None:
    client, s = env
    await _make_user(s, "editor5", _PERMS)
    await _login(client, "editor5")
    eid = await _create(client)

    r = await client.patch(f"/api/v1/events/{eid}", json={"title": "x"}, headers=_cmd())
    assert r.status_code == 422


async def test_edit_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "editor6", _PERMS)
    await _login(client, "editor6")
    eid = await _create(client)

    cid = uuid.uuid4()
    body = {"title": "einmalig", "priority": "low"}
    first = await client.patch(f"/api/v1/events/{eid}", json=body, headers=_cmd(cid, version=1))
    second = await client.patch(f"/api/v1/events/{eid}", json=body, headers=_cmd(cid, version=1))
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(await _updated_events(s, eid)) == 1


async def test_edit_requires_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["events.create"])
    await _login(client, "viewer")
    eid = await _create(client)

    r = await client.patch(f"/api/v1/events/{eid}", json={"title": "x"}, headers=_cmd(version=1))
    assert r.status_code == 403
