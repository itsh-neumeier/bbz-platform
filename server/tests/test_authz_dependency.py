"""`require()` behaviour + the 'every write route declares a permission' contract."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

# Write routes that legitimately have no permission gate (pre-auth / self).
_EXEMPT: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("PUT", "/api/v1/presence"),  # self-service: sets the caller's own presence
}
_WRITE = {"POST", "PUT", "PATCH", "DELETE"}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "authz-test-secret-at-least-32-bytes-long!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


def _declares_permission(route: APIRoute) -> bool:
    for dep in route.dependant.dependencies:
        call = dep.call
        if getattr(call, "_bbz_permission", None) is not None:
            return True
    return False


def test_every_api_v1_write_route_declares_a_permission() -> None:
    from bbz_core.app import create_app

    offenders: list[str] = []
    for route in create_app().routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1"):
            continue
        for method in route.methods & _WRITE:
            if (method, route.path) in _EXEMPT:
                continue
            if not _declares_permission(route):
                offenders.append(f"{method} {route.path}")
    assert not offenders, f"write routes without require(...): {offenders}"


@pytest.fixture
async def make_login(client: httpx.AsyncClient, db: object) -> AsyncIterator[object]:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)

    async def _make(*, permissions: list[str]) -> httpx.AsyncClient:
        user = User(display_name="Op")
        s.add(user)
        await s.flush()
        ident = AuthIdentity(
            user_id=user.id, provider="local", subject=f"op-{uuid.uuid4().hex[:6]}"
        )
        s.add(ident)
        await s.flush()
        s.add(
            LocalCredential(
                auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x")
            )
        )
        if permissions:
            role = Role(key=f"r-{uuid.uuid4().hex[:6]}", name="R")
            s.add(role)
            await s.flush()
            for key in permissions:
                perm = Permission(key=key, area=key.split(".")[0])
                s.add(perm)
                await s.flush()
                s.add(RolePermission(role_id=role.id, permission_id=perm.id, scope="global"))
            s.add(UserRole(user_id=user.id, role_id=role.id))
        await s.commit()
        r = await client.post(
            "/api/v1/auth/login", json={"username": ident.subject, "password": "Wolke7-Bahnhof!x"}
        )
        assert r.status_code == 200, r.text
        return client

    yield _make


async def test_require_401_when_unauthenticated(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/system/info")).status_code == 401


async def test_require_403_then_200(make_login: object) -> None:
    make = make_login  # type: ignore[assignment]

    client_no_perm = await make(permissions=[])
    r403 = await client_no_perm.get("/api/v1/system/info")
    assert r403.status_code == 403
    assert r403.json()["error"]["code"] == "forbidden"
    assert r403.json()["error"]["correlation_id"]

    client_ok = await make(permissions=["system.cluster.view"])
    r200 = await client_ok.get("/api/v1/system/info")
    assert r200.status_code == 200
    assert r200.json()["node_id"]


async def test_me_now_lists_effective_permissions(make_login: object) -> None:
    make = make_login  # type: ignore[assignment]
    client_ok = await make(permissions=["events.view", "events.accept"])
    me = (await client_ok.get("/api/v1/auth/me")).json()
    assert set(me["permissions"]) == {"events.view", "events.accept"}
    assert me["scopes"] == ["global"]
