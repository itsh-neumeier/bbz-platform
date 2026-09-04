"""`require()` behaviour + the 'every write route declares a permission' contract."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import fastapi.routing as _fr
import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

# Write routes that legitimately have no permission gate (pre-auth / self).
_EXEMPT: set[tuple[str, str]] = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password"),  # self-service: proves the current password
    ("POST", "/api/v1/auth/oidc/{provider}/callback"),  # external login — pre-auth
    ("PUT", "/api/v1/presence"),  # self-service: sets the caller's own presence
    ("POST", "/api/v1/auth/totp/enrol"),  # self-service MFA enrolment
    ("POST", "/api/v1/auth/totp/activate"),
    ("DELETE", "/api/v1/auth/totp"),
    ("POST", "/api/v1/auth/mfa-policies/step-up"),  # self-service: re-verify own MFA
    # self-service WebAuthn (E21-06) — acts only on the caller's own credentials
    ("POST", "/api/v1/auth/webauthn/register/options"),
    ("POST", "/api/v1/auth/webauthn/register/verify"),
    ("POST", "/api/v1/auth/webauthn/authenticate/options"),
    ("DELETE", "/api/v1/auth/webauthn/credentials/{credential_id}"),
    # self-service account linking / unlinking (E21-08) — acts on the caller's own account
    ("POST", "/api/v1/auth/identities/local"),
    ("POST", "/api/v1/auth/identities/ldap"),
    ("POST", "/api/v1/auth/identities/oidc/{provider}/start"),
    ("POST", "/api/v1/auth/identities/oidc/{provider}/callback"),
    ("DELETE", "/api/v1/auth/identities/{identity_id}"),
}
_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
_API_V1 = "/api/v1"


def _iter_api_routes(router: object) -> list[tuple[str, APIRoute]]:
    """Every APIRoute reachable from ``router`` with its full ``/api/v1`` path.

    Starlette 1.6 mounts included routers as ``_IncludedRouter`` instead of
    copying their routes, so ``app.routes`` is not flat and a leaf's ``.path`` is
    relative to the router that defined it (``/auth/login``, not
    ``/api/v1/auth/login``). We recurse and prepend the ``/api/v1`` prefix, which
    is baked into a leaf's path only when the leaf sits directly on the v1 router.
    """
    out: list[tuple[str, APIRoute]] = []
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute):
            path = route.path if route.path.startswith(_API_V1) else _API_V1 + route.path
            out.append((path, route))
        if isinstance(route, _fr._IncludedRouter):
            out.extend(_iter_api_routes(route.original_router))
    return out


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

    routes = _iter_api_routes(create_app().router)
    writes = [(m, p) for p, r in routes for m in r.methods & _WRITE]
    assert len(writes) > 80, f"route walker regressed — only found {len(writes)} writes"

    offenders = [
        f"{method} {path}"
        for path, route in routes
        for method in route.methods & _WRITE
        if (method, path) not in _EXEMPT and not _declares_permission(route)
    ]
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
