"""User admin API: create-with-login, deactivate revokes sessions, reset."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "users-admin-test-secret-at-least-32bytes!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _seed_admin(session: AsyncSession, client: httpx.AsyncClient) -> None:
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
    for key in ("users.view", "users.manage", "permissions.manage"):
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


@pytest.fixture
async def admin_client(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _seed_admin(s, client)
    yield client, s


async def test_create_user_with_local_login(admin_client: tuple) -> None:
    client, _ = admin_client
    r = await client.post(
        "/api/v1/users",
        json={
            "display_name": "Bea Operator",
            "local_username": "bea",
            "initial_password": "Wolke7-Bahnhof!x",
        },
    )
    assert r.status_code == 201
    uid = r.json()["id"]
    assert (await client.get(f"/api/v1/users/{uid}")).json()["status"] == "active"


async def test_deactivate_blocks_login_and_revokes_sessions(admin_client: tuple) -> None:
    client, _ = admin_client
    await client.post(
        "/api/v1/users",
        json={
            "display_name": "C",
            "local_username": "carl",
            "initial_password": "Wolke7-Bahnhof!x",
        },
    )
    users = (await client.get("/api/v1/users")).json()
    carl = next(u for u in users if u["display_name"] == "C")

    # carl logs in on his own client
    carl_client = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with carl_client:
        assert (
            await carl_client.post(
                "/api/v1/auth/login", json={"username": "carl", "password": "Wolke7-Bahnhof!x"}
            )
        ).status_code == 200

        d = await client.post(f"/api/v1/users/{carl['id']}/deactivate")
        assert d.status_code == 200 and d.json()["sessions_revoked"] >= 1

        # existing session dead, new login refused
        assert (await carl_client.get("/api/v1/auth/me")).status_code == 401
        relogin = await carl_client.post(
            "/api/v1/auth/login", json={"username": "carl", "password": "Wolke7-Bahnhof!x"}
        )
        assert relogin.status_code == 401


async def test_last_admin_cannot_be_deactivated(admin_client: tuple) -> None:
    client, s = admin_client
    from sqlalchemy import select

    from bbz_core.infra.models.identity import AuthIdentity

    admin_id = (
        await s.execute(select(AuthIdentity.user_id).where(AuthIdentity.subject == "admin"))
    ).scalar_one()
    r = await client.post(f"/api/v1/users/{admin_id}/deactivate")
    assert r.status_code == 409


async def test_password_reset_forces_change(admin_client: tuple) -> None:
    client, _ = admin_client
    await client.post(
        "/api/v1/users",
        json={
            "display_name": "D",
            "local_username": "dora",
            "initial_password": "Wolke7-Bahnhof!x",
        },
    )
    users = (await client.get("/api/v1/users")).json()
    dora = next(u for u in users if u["display_name"] == "D")
    r = await client.post(
        f"/api/v1/users/{dora['id']}/password-reset", json={"new_password": "Neustart-2026!xy"}
    )
    assert r.status_code == 200

    dora_client = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with dora_client:
        login = await dora_client.post(
            "/api/v1/auth/login", json={"username": "dora", "password": "Neustart-2026!xy"}
        )
        assert login.status_code == 200
        assert login.json()["must_change_password"] is True


async def test_weak_reset_password_is_422(admin_client: tuple) -> None:
    client, _ = admin_client
    await client.post(
        "/api/v1/users",
        json={
            "display_name": "E",
            "local_username": "emil",
            "initial_password": "Wolke7-Bahnhof!x",
        },
    )
    users = (await client.get("/api/v1/users")).json()
    emil = next(u for u in users if u["display_name"] == "E")
    r = await client.post(
        f"/api/v1/users/{emil['id']}/password-reset", json={"new_password": "weak"}
    )
    assert r.status_code == 422


async def test_requires_users_manage(client: httpx.AsyncClient, db: object) -> None:
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
    assert (await client.post("/api/v1/users", json={"display_name": "X"})).status_code == 403
