"""Technical-endpoint admin API: CRUD, number patterns, rights, audit (E15-10)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint, TechnicalEndpointNumber

_MANAGE = ["technical_endpoints.view", "technical_endpoints.manage", "door.configure"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "teadmin-test-secret-at-least-32-bytes-okok!"
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


async def _count(s: AsyncSession, model: type) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def _audit_count(s: AsyncSession, action: str) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_create_read_update_delete_an_endpoint_is_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "te", _MANAGE)
    await _login(client, "te")

    created = await client.post(
        "/api/v1/technical-endpoints",
        json={
            "name": "Haupttor",
            "type": "door_station",
            "site": "Nord",
            "default_priority": "high",
            "numbers": [{"called_pattern": "200", "cti_route_point": "RP_TOR"}],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    eid = body["id"]
    assert body["active_config_version"] == 1
    assert body["numbers"][0]["called_pattern"] == "200"
    assert await _audit_count(s, "TECHNICAL_ENDPOINT_CREATED") == 1

    got = await client.get(f"/api/v1/technical-endpoints/{eid}")
    assert got.status_code == 200 and got.json()["name"] == "Haupttor"

    listed = await client.get("/api/v1/technical-endpoints")
    assert [e["id"] for e in listed.json()] == [eid]

    patched = await client.patch(
        f"/api/v1/technical-endpoints/{eid}",
        json={"name": "Haupttor Nord", "numbers": [{"called_pattern": "201"}]},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Haupttor Nord"
    assert patched.json()["active_config_version"] == 2  # bumped
    assert patched.json()["numbers"][0]["called_pattern"] == "201"
    assert await _audit_count(s, "TECHNICAL_ENDPOINT_UPDATED") == 1

    assert (await client.delete(f"/api/v1/technical-endpoints/{eid}")).status_code == 204
    assert (await client.get(f"/api/v1/technical-endpoints/{eid}")).status_code == 404
    assert await _count(s, TechnicalEndpoint) == 0
    assert await _count(s, TechnicalEndpointNumber) == 0  # cascaded
    assert await _audit_count(s, "TECHNICAL_ENDPOINT_DELETED") == 1


async def test_an_unknown_type_or_priority_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "te2", _MANAGE)
    await _login(client, "te2")
    r = await client.post("/api/v1/technical-endpoints", json={"name": "x", "type": "teleporter"})
    assert r.status_code == 422


async def test_a_noop_patch_does_not_bump_the_config_version(env: tuple) -> None:
    client, s = env
    await _make_user(s, "te3", _MANAGE)
    await _login(client, "te3")
    eid = (
        await client.post("/api/v1/technical-endpoints", json={"name": "BMA 1", "type": "bma"})
    ).json()["id"]

    r = await client.patch(f"/api/v1/technical-endpoints/{eid}", json={"name": "BMA 1"})
    assert r.status_code == 200 and r.json()["active_config_version"] == 1
    assert await _audit_count(s, "TECHNICAL_ENDPOINT_UPDATED") == 0


async def test_manage_permission_is_required_for_writes(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["technical_endpoints.view"])
    await _make_user(s, "mgr", _MANAGE)
    await _login(client, "mgr")
    eid = (
        await client.post(
            "/api/v1/technical-endpoints", json={"name": "Tor", "type": "door_station"}
        )
    ).json()["id"]

    await _login(client, "viewer")
    assert (
        await client.post("/api/v1/technical-endpoints", json={"name": "y", "type": "custom"})
    ).status_code == 403
    assert (
        await client.patch(f"/api/v1/technical-endpoints/{eid}", json={"name": "z"})
    ).status_code == 403
    assert (await client.delete(f"/api/v1/technical-endpoints/{eid}")).status_code == 403
    # reads still work
    assert (await client.get(f"/api/v1/technical-endpoints/{eid}")).status_code == 200


async def test_unauthenticated_is_401(env: tuple) -> None:
    client, _ = env
    assert (await client.get("/api/v1/technical-endpoints")).status_code == 401
