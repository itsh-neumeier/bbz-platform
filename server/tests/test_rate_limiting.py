"""E23-04: cluster-wide rate limiting on the abuse-prone endpoints."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "rate-limit-test-jwt-at-least-32-bytes-ok!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_RATE_LIMIT_LOGIN"] = "3/60"
    os.environ["BBZ_RATE_LIMIT_MFA"] = "2/60"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    settings_mod.get_settings.cache_clear()
    yield
    for k in ("BBZ_RATE_LIMIT_LOGIN", "BBZ_RATE_LIMIT_MFA"):
        os.environ.pop(k, None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    settings_mod.get_settings.cache_clear()


async def _make_user(s: AsyncSession, username: str) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    pw = hash_password("Wolke7-Bahnhof!x")
    s.add(LocalCredential(auth_identity_id=ident.id, password_hash=pw))
    await s.commit()
    return u.id


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    assert isinstance(db, AsyncSession)
    yield client, db


async def _try_login(c: httpx.AsyncClient, pw: str = "wrong") -> httpx.Response:
    return await c.post("/api/v1/auth/login", json={"username": "u", "password": pw})


async def test_login_is_throttled_by_ip_and_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "u")

    codes = [(await _try_login(client)).status_code for _ in range(3)]
    assert codes == [401, 401, 401]  # 3 allowed (bad creds)

    r = await _try_login(client)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    assert r.json()["error"]["code"] == "rate_limited"

    from bbz_core.infra.models.audit import AuditEvent

    await s.rollback()
    rows = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action == "RATE_LIMIT_TRIGGERED")))
        .scalars()
        .all()
    )
    assert rows and rows[0].after["rule"] == "login"
    assert "wrong" not in str(rows[0].after) and "Wolke7" not in str(rows[0].after)


async def test_the_counter_is_shared_across_clients(env: tuple) -> None:
    client, s = env
    await _make_user(s, "u")
    other = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]

    assert (await _try_login(client)).status_code == 401
    assert (await _try_login(other)).status_code == 401
    assert (await _try_login(client)).status_code == 401
    # 4th hit against the shared bucket, from either client -> 429
    assert (await _try_login(other)).status_code == 429
    await other.aclose()


async def test_a_disabled_rule_never_throttles(env: tuple) -> None:
    client, s = env
    from bbz_core import settings as settings_mod

    await _make_user(s, "u")
    os.environ["BBZ_RATE_LIMIT_LOGIN"] = "0/60"
    settings_mod.get_settings.cache_clear()

    codes = {(await _try_login(client)).status_code for _ in range(8)}
    assert codes == {401}


async def test_the_window_resets(env: tuple) -> None:
    client, s = env
    from bbz_core import settings as settings_mod

    await _make_user(s, "u")
    os.environ["BBZ_RATE_LIMIT_LOGIN"] = "2/1"  # 2 per second
    settings_mod.get_settings.cache_clear()

    assert (await _try_login(client)).status_code == 401
    assert (await _try_login(client)).status_code == 401
    assert (await _try_login(client)).status_code == 429
    await asyncio.sleep(1.2)
    assert (await _try_login(client)).status_code == 401  # new window


async def test_mfa_activate_is_throttled_per_user(env: tuple) -> None:
    client, s = env
    uid = await _make_user(s, "u")

    from bbz_core.auth.sessions import SessionService
    from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore

    issued = await SessionService(SqlAlchemySessionStore(s)).start(
        uid, client_id=None, workplace_id=None, user_agent="test"
    )
    await s.commit()
    client.cookies.set("bbz_access", issued.access_token)

    codes = [
        (await client.post("/api/v1/auth/totp/activate", json={"code": "000000"})).status_code
        for _ in range(4)
    ]
    assert codes.count(429) == 2  # limit 2/60 -> the 3rd and 4th are blocked
