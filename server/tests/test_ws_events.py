"""WebSocket event stream: authorization + origin check (E03-14).

The catch-up / ordering / heartbeat / live behaviour is shared with SSE through
``event_feed`` and is covered in test_event_stream.py.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.ws import _authorize, _origin_allowed


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "ws-test-secret-at-least-32-bytes-long-ok!!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    os.environ.pop("BBZ_CORS_ALLOW_ORIGINS", None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@dataclass
class _FakeWS:
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    query_params: dict[str, str] = field(default_factory=dict)


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


async def _access_token(client: httpx.AsyncClient, username: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text
    return client.cookies["bbz_access"]


async def test_authorize_accepts_valid_session_with_events_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wsviewer", ["events.view"])
    token = await _access_token(client, "wsviewer")
    assert await _authorize(_FakeWS(cookies={"bbz_access": token})) is True


async def test_authorize_rejects_missing_token(env: tuple) -> None:
    assert await _authorize(_FakeWS()) is False


async def test_authorize_rejects_without_events_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wsnope", ["events.create"])
    token = await _access_token(client, "wsnope")
    assert await _authorize(_FakeWS(cookies={"bbz_access": token})) is False


async def test_authorize_accepts_token_via_query_param(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wsq", ["events.view"])
    token = await _access_token(client, "wsq")
    assert await _authorize(_FakeWS(query_params={"access_token": token})) is True


async def test_authorize_rejects_disallowed_origin(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wso", ["events.view"])
    token = await _access_token(client, "wso")
    os.environ["BBZ_CORS_ALLOW_ORIGINS"] = '["https://ok.example"]'
    from bbz_core.settings import get_settings

    get_settings.cache_clear()
    ws = _FakeWS(cookies={"bbz_access": token}, headers={"origin": "https://evil.example"})
    assert await _authorize(ws) is False


def test_origin_allowed_without_allowlist() -> None:
    assert _origin_allowed(_FakeWS(headers={"origin": "https://anything"})) is True
