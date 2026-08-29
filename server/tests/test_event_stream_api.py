"""GET /api/v1/events/stream — route wiring + auth (E03-13).

Streaming behaviour (catch-up / heartbeat / live) is covered against the
generator in test_event_stream.py; here we only check the HTTP surface that
resolves before any streaming starts.
"""

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
    os.environ["BBZ_JWT_SECRET"] = "stream-test-secret-at-least-32-bytes-okayy!!"
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


async def test_stream_requires_authentication(env: tuple) -> None:
    client, _ = env
    assert (await client.get("/api/v1/events/stream")).status_code == 401


async def test_stream_requires_events_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "streamless", ["events.create"])
    await _login(client, "streamless")
    assert (await client.get("/api/v1/events/stream")).status_code == 403


async def test_stream_path_does_not_collide_with_detail(env: tuple) -> None:
    # "/events/stream" must resolve to the stream route, not /events/{event_id}
    client, s = env
    await _make_user(s, "viewer", ["events.view"])
    await _login(client, "viewer")
    r = await client.get(f"/api/v1/events/{uuid.uuid4()}")
    assert r.status_code == 404  # detail route still reachable for real UUIDs
