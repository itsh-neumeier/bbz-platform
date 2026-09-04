"""POST /api/v1/auth/password — self-service local password change (E07-02 / #97)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.identity import AuthIdentity, LocalCredential
from bbz_core.infra.models.session import Session

_OLD = "Wolke7-Bahnhof!x"
_NEW = "Fjord-Nebel-42!x"


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "pwchange-test-secret-at-least-32-bytes-ok!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_user(
    s: AsyncSession, username: str, *, password: str = _OLD, must_change: bool = False
) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import User

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(
            auth_identity_id=ident.id,
            password_hash=hash_password(password),
            must_change=must_change,
        )
    )
    await s.commit()
    return u.id


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _login(client: httpx.AsyncClient, username: str, password: str = _OLD) -> None:
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


async def _cred(s: AsyncSession, username: str) -> LocalCredential:
    return (
        await s.execute(
            select(LocalCredential)
            .join(AuthIdentity, AuthIdentity.id == LocalCredential.auth_identity_id)
            .where(AuthIdentity.subject == username)
        )
    ).scalar_one()


async def test_change_password_rotates_the_hash_and_clears_must_change(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", must_change=True)
    await _login(client, "op")

    r = await client.post(
        "/api/v1/auth/password",
        json={"current_password": _OLD, "new_password": _NEW},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"other_sessions_revoked": 0}

    s.expire_all()
    cred = await _cred(s, "op")
    assert cred.must_change is False
    assert cred.password_changed_at is not None

    # the old password no longer authenticates, the new one does
    bad = await client.post("/api/v1/auth/login", json={"username": "op", "password": _OLD})
    assert bad.status_code == 401
    good = await client.post("/api/v1/auth/login", json={"username": "op", "password": _NEW})
    assert good.status_code == 200


async def test_change_password_is_audited_once(env: tuple) -> None:
    client, s = env
    uid = await _make_user(s, "op2")
    await _login(client, "op2")
    assert (
        await client.post(
            "/api/v1/auth/password",
            json={"current_password": _OLD, "new_password": _NEW},
        )
    ).status_code == 200
    rows = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action == "PASSWORD_CHANGED")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].actor_user_id == uid
    assert rows[0].target_id == str(uid)


async def test_wrong_current_password_is_rejected_and_changes_nothing(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3")
    await _login(client, "op3")
    before = (await _cred(s, "op3")).password_hash

    r = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-the-password", "new_password": _NEW},
    )
    assert r.status_code == 401
    s.expire_all()
    assert (await _cred(s, "op3")).password_hash == before


async def test_new_password_must_differ_from_current(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4")
    await _login(client, "op4")
    r = await client.post(
        "/api/v1/auth/password",
        json={"current_password": _OLD, "new_password": _OLD},
    )
    assert r.status_code == 422


async def test_new_password_must_meet_the_policy(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5")
    await _login(client, "op5")
    r = await client.post(
        "/api/v1/auth/password",
        json={"current_password": _OLD, "new_password": "short"},
    )
    assert r.status_code == 422
    assert "12 characters" in r.text


async def test_other_sessions_are_revoked_but_the_current_one_survives(env: tuple) -> None:
    client, s = env
    uid = await _make_user(s, "op6")
    # a second, independent session for the same account (a kiosk / other browser)
    other = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    await _login(other, "op6")
    await _login(client, "op6")
    assert (
        await s.execute(
            select(func.count())
            .select_from(Session)
            .where(Session.user_id == uid, Session.revoked_at.is_(None))
        )
    ).scalar_one() == 2

    r = await client.post(
        "/api/v1/auth/password",
        json={"current_password": _OLD, "new_password": _NEW},
    )
    assert r.status_code == 200
    assert r.json()["other_sessions_revoked"] == 1

    # the caller's own session still works …
    assert (await client.get("/api/v1/auth/me")).status_code == 200
    # … the other one is gone
    assert (await other.get("/api/v1/auth/me")).status_code == 401
    await other.aclose()


async def test_password_change_needs_authentication(env: tuple) -> None:
    client, _ = env
    r = await client.post(
        "/api/v1/auth/password",
        json={"current_password": _OLD, "new_password": _NEW},
    )
    assert r.status_code == 401


async def test_me_reports_must_change_and_it_clears_after_the_change(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op7", must_change=True)
    await _login(client, "op7")

    assert (await client.get("/api/v1/auth/me")).json()["must_change_password"] is True
    assert (
        await client.post(
            "/api/v1/auth/password",
            json={"current_password": _OLD, "new_password": _NEW},
        )
    ).status_code == 200
    assert (await client.get("/api/v1/auth/me")).json()["must_change_password"] is False
