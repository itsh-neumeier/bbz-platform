"""POST /api/v1/events — permission, validation, idempotency (E03-06)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.domain_events import DomainEvent


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "events-test-secret-at-least-32-bytes-okay!!"
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


def _headers(command_id: uuid.UUID | None = None) -> dict[str, str]:
    return {"X-Command-Id": str(command_id or uuid.uuid4())}


async def _event_count(s: AsyncSession) -> int:
    return (await s.execute(select(func.count()).select_from(DomainEvent))).scalar_one()


async def test_create_event_happy_path(env: tuple) -> None:
    client, s = env
    await _make_user(s, "leitstelle", ["events.create"])
    await _login(client, "leitstelle")

    r = await client.post(
        "/api/v1/events",
        json={"title": "Weichenstörung W12", "priority": "high"},
        headers=_headers(),
    )
    assert r.status_code == 201, r.text
    payload = r.json()
    assert payload["status"] == "new"
    assert payload["version"] == 1
    assert r.headers["Location"] == f"/api/v1/events/{payload['id']}"

    rows = (
        (await s.execute(select(DomainEvent).where(DomainEvent.aggregate_id == payload["id"])))
        .scalars()
        .all()
    )
    assert [row.event_type for row in rows] == ["EVENT_CREATED"]


async def test_create_event_forbidden_without_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "gast", [])
    await _login(client, "gast")

    r = await client.post(
        "/api/v1/events", json={"title": "x", "priority": "low"}, headers=_headers()
    )
    assert r.status_code == 403
    assert await _event_count(s) == 0


async def test_create_event_invalid_priority(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op1", ["events.create"])
    await _login(client, "op1")

    r = await client.post(
        "/api/v1/events", json={"title": "x", "priority": "urgent"}, headers=_headers()
    )
    assert r.status_code == 422
    assert await _event_count(s) == 0


async def test_missing_command_id_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", ["events.create"])
    await _login(client, "op2")

    r = await client.post("/api/v1/events", json={"title": "x", "priority": "low"})
    assert r.status_code == 422


async def test_duplicate_command_replays_without_a_second_event(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", ["events.create"])
    await _login(client, "op3")

    cid = uuid.uuid4()
    body = {"title": "Rauch am Bahnsteig 4", "priority": "critical"}
    first = await client.post("/api/v1/events", json=body, headers=_headers(cid))
    second = await client.post("/api/v1/events", json=body, headers=_headers(cid))

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert await _event_count(s) == 1


async def test_same_command_id_different_body_conflicts(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4", ["events.create"])
    await _login(client, "op4")

    cid = uuid.uuid4()
    await client.post(
        "/api/v1/events", json={"title": "A", "priority": "low"}, headers=_headers(cid)
    )
    clash = await client.post(
        "/api/v1/events", json={"title": "B", "priority": "low"}, headers=_headers(cid)
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "conflict"
    assert await _event_count(s) == 1
