"""Mock scenario driver over HTTP (E11-05's own "Szenarien per API/Config
auslösbar"): ``POST /telephony/_mock/simulate-incoming`` drives the mock
provider's ``simulate_incoming()`` and pumps what it emits through the real
ingest pipeline, since no background worker otherwise drains a telephony
provider's event stream."""

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
    os.environ["BBZ_JWT_SECRET"] = "mock-scenario-secret-at-least-32-bytes-ok!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_user(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
    from sqlalchemy import select

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
async def env(client: httpx.AsyncClient, db: object) -> AsyncIterator[httpx.AsyncClient]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def test_requires_the_machine_only_permission(env: httpx.AsyncClient, db: object) -> None:
    client = env
    await _make_user(db, "weak", ["calls.view"])  # type: ignore[arg-type]
    await _login(client, "weak")
    r = await client.post(
        "/api/v1/telephony/_mock/simulate-incoming",
        json={"from_number": "+49911500", "to_line": "1001"},
        headers=_cmd(),
    )
    assert r.status_code == 403


async def test_simulates_an_incoming_call_visible_in_the_ringing_queue(
    env: httpx.AsyncClient, db: object
) -> None:
    client = env
    await _make_user(db, "sim", ["calls.simulate_mock_scenario", "calls.view"])  # type: ignore[arg-type]
    await _login(client, "sim")

    r = await client.post(
        "/api/v1/telephony/_mock/simulate-incoming",
        json={"from_number": "+49911500", "to_line": "1001", "display_name": "EVU Nord"},
        headers=_cmd(),
    )
    assert r.status_code == 200, r.text
    scid = r.json()["source_call_id"]
    assert scid

    ringing = (await client.get("/api/v1/calls/ringing")).json()["items"]
    assert any(it["participants"] for it in ringing), ringing
    matched = [it for it in ringing if any(p["number"] == "+49911500" for p in it["participants"])]
    assert len(matched) == 1, ringing


async def test_404s_when_the_active_provider_is_not_a_mock(
    env: httpx.AsyncClient, db: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = env
    await _make_user(db, "sim2", ["calls.simulate_mock_scenario"])  # type: ignore[arg-type]
    await _login(client, "sim2")

    class _RealishProvider:
        def info(self) -> object:
            class _Info:
                mock = False

            return _Info()

    async def _fake_active_provider() -> object:
        return _RealishProvider()

    import bbz_core.api.v1.telephony as telephony_module

    monkeypatch.setattr(telephony_module, "active_telephony_provider", _fake_active_provider)

    r = await client.post(
        "/api/v1/telephony/_mock/simulate-incoming",
        json={"from_number": "+49911500", "to_line": "1001"},
        headers=_cmd(),
    )
    assert r.status_code == 404
