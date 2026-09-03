"""Admin integrations overview (#724) — registry + settings-store selection."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_VIEW = ["integrations.view", "system.settings.manage"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "admin-int-test-secret-at-least-32-bytes-ok"
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


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


def _domain(body: dict, name: str) -> dict:
    return next(d for d in body["domains"] if d["domain"] == name)


async def test_overview_lists_the_four_domains_with_discoverable_adapters(env: tuple) -> None:
    client, s = env
    await _make_user(s, "ig1", _VIEW)
    await _login(client, "ig1")

    r = await client.get("/api/v1/admin/integrations")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [d["domain"] for d in body["domains"]] == ["telephony", "video", "weather", "monitor"]

    monitor = _domain(body, "monitor")
    ids = {a["id"] for a in monitor["available"]}
    assert "monitor_mock" in ids  # the repo ships this scaffold
    assert monitor["active_id"] == "monitor_mock"  # the default
    assert monitor["source"] == "default"


async def test_a_selection_override_is_reflected(env: tuple, monkeypatch) -> None:
    from bbz_core.settings import get_settings

    # a non-default value so `source` can tell env from the code default
    monkeypatch.setenv("BBZ_WEATHER_INTEGRATION_ID", "dwd_staging")
    get_settings.cache_clear()

    client, s = env
    await _make_user(s, "ig2", _VIEW)
    await _login(client, "ig2")

    assert (
        _domain((await client.get("/api/v1/admin/integrations")).json(), "weather")["source"]
        == "environment"
    )

    await client.put(
        "/api/v1/admin/settings/integrations",
        json={"values": {"integrations.weather": "dwd"}},
    )
    weather = _domain((await client.get("/api/v1/admin/integrations")).json(), "weather")
    assert weather["active_id"] == "dwd" and weather["source"] == "database"


async def test_overview_needs_integrations_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "ig3", ["users.view"])
    await _login(client, "ig3")
    assert (await client.get("/api/v1/admin/integrations")).status_code == 403
