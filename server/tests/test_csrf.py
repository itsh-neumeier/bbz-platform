"""E23-05: CSRF protection for cookie-authenticated writes.

The contract test is the important one — it walks every ``/api/v1`` write
operation in the OpenAPI schema and fails if one is neither guarded by
``CsrfMiddleware`` nor on the documented bearer-only allowlist.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.csrf import CSRF_TOKEN_EXEMPT, CsrfMiddleware, csrf_guards
from bbz_core.auth.csrf import csrf_token_valid, issue_csrf_token

# --- write operations that legitimately never need a CSRF token --------------
# Machine clients authenticate with ``Authorization: Bearer`` and carry no
# ambient cookie for a foreign page to ride on. Keep this list tiny and
# justified; docs/security/csrf.md explains each entry.
_BEARER_ONLY: set[tuple[str, str]] = {
    ("POST", "/api/v1/telephony/events"),  # inbound provider webhook (service account)
}


def _write_ops() -> list[tuple[str, str]]:
    os.environ.setdefault("BBZ_JWT_SECRET", "csrf-test-secret-at-least-32-bytes-long!!")
    from bbz_core.app import create_app

    spec = create_app().openapi()
    ops: list[tuple[str, str]] = []
    for path, methods in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        for method in methods:
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                ops.append((method.upper(), path))
    return ops


def test_every_api_v1_write_is_csrf_protected() -> None:
    unprotected: list[str] = []
    for method, path in _write_ops():
        if (method, path) in _BEARER_ONLY:
            continue  # machine clients — immune to CSRF by construction
        if path in CSRF_TOKEN_EXEMPT:
            continue  # pre-auth — Origin/Referer checked, no token can exist yet
        if not csrf_guards(method, path):
            unprotected.append(f"{method} {path}")
    assert not unprotected, f"write routes with no CSRF double-submit check: {unprotected}"


def test_csrf_guards_the_ordinary_writes_but_not_the_exemptions() -> None:
    assert csrf_guards("POST", "/api/v1/events")
    assert csrf_guards("DELETE", "/api/v1/roles/{role_id}")
    assert not csrf_guards("GET", "/api/v1/events")
    assert not csrf_guards("POST", "/api/v1/auth/login")  # token-exempt
    assert not csrf_guards("POST", "/healthz")  # outside /api/v1


def test_the_token_exempt_set_is_exactly_the_pre_auth_writes() -> None:
    # A change here must be deliberate — every entry skips the double-submit
    # check (Origin/Referer is still enforced).
    assert sorted(CSRF_TOKEN_EXEMPT) == [
        "/api/v1/auth/login",
        "/api/v1/auth/oidc/{provider}/callback",
    ]


def test_middleware_is_installed() -> None:
    from bbz_core.app import create_app

    assert CsrfMiddleware in {m.cls for m in create_app().user_middleware}


def test_csrf_token_is_bound_to_its_session() -> None:
    sid_a, sid_b = uuid.uuid4(), uuid.uuid4()
    token = issue_csrf_token(sid_a)
    assert csrf_token_valid(token, session_id=sid_a)
    assert csrf_token_valid(token)  # signature-only (the /refresh path)
    assert not csrf_token_valid(token, session_id=sid_b)
    assert not csrf_token_valid("not-a-token")
    assert not csrf_token_valid(f"{token}tampered")


# --- integration (needs PostgreSQL, like the rest of the suite) --------------


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "csrf-test-secret-at-least-32-bytes-long!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    for key in ("BBZ_CSRF_ENABLED",):
        os.environ.pop(key, None)
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


async def _login(c: httpx.AsyncClient, username: str = "op") -> None:
    r = await c.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _new_event(extra_headers: dict[str, str] | None = None) -> dict[str, object]:
    return {
        "json": {"title": "x", "priority": "low"},
        "headers": {"X-Command-Id": str(uuid.uuid4()), **(extra_headers or {})},
    }


async def test_a_cookie_write_without_the_token_is_blocked(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.create"])
    await _login(client)

    r = await client.post("/api/v1/events", **_new_event({"x-csrf-token": ""}))
    assert r.status_code == 403
    assert r.json()["error"]["details"]["reason"] == "csrf_token_missing"


async def test_a_cookie_write_with_the_mirrored_token_passes(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.create"])
    await _login(client)

    # conftest mirrors the bbz_csrf cookie into X-CSRF-Token, like the SPA
    r = await client.post("/api/v1/events", **_new_event())
    assert r.status_code == 201, r.text


async def test_a_delete_without_the_token_is_blocked(env: tuple) -> None:
    from bbz_core.infra.models.rbac import Role

    client, s = env
    await _make_user(s, "op", ["roles.manage"])
    await _login(client)
    victim = Role(key="victim", name="V")
    s.add(victim)
    await s.commit()

    r = await client.delete(f"/api/v1/roles/{victim.id}", headers={"x-csrf-token": "nope"})
    assert r.status_code == 403
    assert r.json()["error"]["details"]["reason"] == "csrf_token_mismatch"


async def test_a_bad_origin_is_rejected_even_with_a_valid_token(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.create"])
    await _login(client)

    r = await client.post("/api/v1/events", **_new_event({"origin": "https://evil.example"}))
    assert r.status_code == 403
    assert r.json()["error"]["details"]["reason"] == "origin_not_allowed"


async def test_the_same_origin_header_is_allowed(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.create"])
    await _login(client)

    r = await client.post("/api/v1/events", **_new_event({"origin": "http://testserver"}))
    assert r.status_code == 201, r.text


async def test_a_token_from_another_session_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.create"])
    await _login(client)

    foreign = issue_csrf_token(uuid.uuid4())  # correctly signed, wrong session
    client.cookies.delete("bbz_csrf")
    client.cookies.set("bbz_csrf", foreign)  # cookie == header, but not this session
    r = await client.post("/api/v1/events", **_new_event({"x-csrf-token": foreign}))
    assert r.status_code == 403
    assert r.json()["error"]["details"]["reason"] == "csrf_token_invalid"


async def test_bearer_clients_are_exempt(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["events.create"])
    await _login(client)
    access = client.cookies["bbz_access"]

    bare = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with bare:
        r = await bare.post(
            "/api/v1/events",
            json={"title": "x", "priority": "low"},
            headers={"X-Command-Id": str(uuid.uuid4()), "authorization": f"Bearer {access}"},
        )
    assert r.status_code == 201, r.text


async def test_logout_and_refresh_need_the_token(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", [])
    await _login(client)

    assert (
        await client.post("/api/v1/auth/logout", headers={"x-csrf-token": ""})
    ).status_code == 403
    assert (
        await client.post("/api/v1/auth/refresh", headers={"x-csrf-token": ""})
    ).status_code == 403
    assert (await client.post("/api/v1/auth/refresh")).status_code == 204  # mirrored
    assert (await client.post("/api/v1/auth/logout")).status_code == 204


async def test_a_cookieless_write_is_left_for_the_auth_layer(env: tuple) -> None:
    client, _ = env
    # no session cookie at all -> CsrfMiddleware ignores it; auth returns 401
    r = await client.post(
        "/api/v1/events",
        json={"title": "x", "priority": "low"},
        headers={"X-Command-Id": str(uuid.uuid4()), "x-csrf-token": ""},
    )
    assert r.status_code == 401


async def test_disabling_csrf_lets_a_tokenless_cookie_write_through(env: tuple) -> None:
    from bbz_core import settings as settings_mod

    client, s = env
    await _make_user(s, "op", ["events.create"])
    await _login(client)

    os.environ["BBZ_CSRF_ENABLED"] = "false"
    settings_mod.get_settings.cache_clear()
    try:
        r = await client.post("/api/v1/events", **_new_event({"x-csrf-token": ""}))
        assert r.status_code == 201, r.text
    finally:
        os.environ.pop("BBZ_CSRF_ENABLED", None)
        settings_mod.get_settings.cache_clear()
