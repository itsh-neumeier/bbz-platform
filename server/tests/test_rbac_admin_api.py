"""RBAC admin API: CRUD, immediate effect, idempotency, last-admin guard."""

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
    os.environ["BBZ_JWT_SECRET"] = "rbac-admin-test-secret-at-least-32-bytes!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _seed_admin(session: AsyncSession, client: httpx.AsyncClient) -> uuid.UUID:
    """Create an operator with roles.manage + permissions.manage and log in."""
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    admin = User(display_name="Admin")
    session.add(admin)
    await session.flush()
    ident = AuthIdentity(user_id=admin.id, provider="local", subject="admin")
    session.add(ident)
    await session.flush()
    session.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    role = Role(key="administrator", name="Administrator")
    session.add(role)
    await session.flush()
    for key in (
        "roles.view",
        "roles.manage",
        "permissions.manage",
        "users.view",
        "system.cluster.view",
    ):
        p = Permission(key=key, area=key.split(".")[0])
        session.add(p)
        await session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
    session.add(UserRole(user_id=admin.id, role_id=role.id))
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text
    return admin.id


@pytest.fixture
async def admin_client(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _seed_admin(s, client)
    yield client, s


async def test_role_crud_and_idempotent_create(admin_client: tuple) -> None:
    client, _ = admin_client
    r1 = await client.post("/api/v1/roles", json={"key": "disponent", "name": "Disponent"})
    assert r1.status_code == 201
    r2 = await client.post("/api/v1/roles", json={"key": "disponent", "name": "Disponent 2"})
    assert r2.status_code == 201
    assert r2.json()["id"] == r1.json()["id"]  # no duplicate

    roles = (await client.get("/api/v1/roles")).json()
    assert {"administrator", "disponent"} <= {r["key"] for r in roles}


async def test_new_role_takes_effect_immediately(admin_client: tuple) -> None:
    client, s = admin_client
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User

    op = User(display_name="Op")
    s.add(op)
    await s.flush()
    ident = AuthIdentity(user_id=op.id, provider="local", subject="op1")
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    await s.commit()

    role = (await client.post("/api/v1/roles", json={"key": "viewer", "name": "Viewer"})).json()
    await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json=[{"permission_key": "system.cluster.view"}],
    )
    await client.post(f"/api/v1/users/{op.id}/roles", json={"role_id": role["id"]})

    op_client = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with op_client:
        login = await op_client.post(
            "/api/v1/auth/login", json={"username": "op1", "password": "Wolke7-Bahnhof!x"}
        )
        assert login.status_code == 200
        # immediately allowed — no restart, no cache flush
        assert (await op_client.get("/api/v1/system/info")).status_code == 200


async def test_unknown_permission_key_is_422(admin_client: tuple) -> None:
    client, _ = admin_client
    role = (await client.post("/api/v1/roles", json={"key": "xx", "name": "X"})).json()
    r = await client.put(
        f"/api/v1/roles/{role['id']}/permissions",
        json=[{"permission_key": "events.telepathy"}],
    )
    assert r.status_code == 422


async def test_last_admin_cannot_be_disarmed(admin_client: tuple) -> None:
    client, s = admin_client
    from sqlalchemy import select

    from bbz_core.infra.models.rbac import Role

    admin_role = (await s.execute(select(Role).where(Role.key == "administrator"))).scalar_one()
    # stripping permissions.manage from the only admin role -> 409
    r = await client.put(
        f"/api/v1/roles/{admin_role.id}/permissions",
        json=[{"permission_key": "roles.view"}],
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


async def test_requires_manage_permission(client: httpx.AsyncClient, db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User

    u = User(display_name="Nobody")
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject="nobody")
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    await s.commit()
    await client.post(
        "/api/v1/auth/login", json={"username": "nobody", "password": "Wolke7-Bahnhof!x"}
    )
    assert (await client.post("/api/v1/roles", json={"key": "z", "name": "Z"})).status_code == 403
