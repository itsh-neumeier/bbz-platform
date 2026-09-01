"""Access tokens, session lifecycle, and the /auth/* endpoints."""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.auth.sessions import (
    SessionExpiredError,
    SessionNotFoundError,
    SessionRecord,
    SessionService,
)
from bbz_core.auth.tokens import (
    AccessClaims,
    TokenError,
    decode_access_token,
    issue_access_token,
)


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "unit-test-secret-at-least-32-bytes-long!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


# --- access tokens (no DB) ------------------------------------------------


def test_access_token_roundtrip() -> None:
    uid, sid = uuid.uuid4(), uuid.uuid4()
    claims = decode_access_token(issue_access_token(uid, sid))
    assert claims == AccessClaims(uid, sid)


def test_access_token_rejects_garbage_and_wrong_secret() -> None:
    with pytest.raises(TokenError):
        decode_access_token("not.a.jwt")
    tok = issue_access_token(uuid.uuid4(), uuid.uuid4())
    os.environ["BBZ_JWT_SECRET"] = "a-different-secret-also-32-bytes-plus-xx!!"
    from bbz_core import settings as sm

    sm.get_settings.cache_clear()
    with pytest.raises(TokenError):
        decode_access_token(tok)


# --- session service (fake store) ---------------------------------------


class FakeSessionStore:
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, SessionRecord] = {}
        self.by_hash: dict[str, uuid.UUID] = {}

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        refresh_hash: str,
        expires_at: _dt.datetime,
        client_id: str | None = None,
        workplace_id: str | None = None,
        user_agent: str | None = None,
        mfa_verified: bool = False,
    ) -> uuid.UUID:
        sid = uuid.uuid4()
        mfa_at = _dt.datetime.now(_dt.UTC) if mfa_verified else None
        self.rows[sid] = SessionRecord(sid, user_id, expires_at, None, mfa_at)
        self.by_hash[refresh_hash] = sid
        return sid

    async def get_active_by_refresh(self, refresh_hash: str) -> SessionRecord | None:
        sid = self.by_hash.get(refresh_hash)
        rec = self.rows.get(sid) if sid else None
        return rec if rec and rec.revoked_at is None else None

    async def get_active(self, session_id: uuid.UUID) -> SessionRecord | None:
        rec = self.rows.get(session_id)
        return rec if rec and rec.revoked_at is None else None

    async def touch(self, session_id: uuid.UUID) -> None: ...

    async def mark_mfa_verified(self, session_id: uuid.UUID) -> None:
        r = self.rows[session_id]
        self.rows[session_id] = SessionRecord(
            r.id, r.user_id, r.expires_at, r.revoked_at, _dt.datetime.now(_dt.UTC)
        )

    async def revoke(self, session_id: uuid.UUID) -> None:
        r = self.rows[session_id]
        now = _dt.datetime.now(_dt.UTC)
        self.rows[session_id] = SessionRecord(r.id, r.user_id, r.expires_at, now)

    async def revoke_by_refresh(self, refresh_hash: str) -> None:
        await self.revoke(self.by_hash[refresh_hash])

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        n = 0
        for sid, r in list(self.rows.items()):
            if r.user_id == user_id and r.revoked_at is None:
                await self.revoke(sid)
                n += 1
        return n


async def test_session_start_refresh_revoke() -> None:
    store = FakeSessionStore()
    svc = SessionService(store)
    uid = uuid.uuid4()
    issued = await svc.start(uid)
    assert await svc.is_active(issued.session_id)

    access, sid = await svc.refresh(issued.refresh_token)
    assert decode_access_token(access).session_id == sid == issued.session_id

    await svc.revoke_by_refresh(issued.refresh_token)
    assert not await svc.is_active(issued.session_id)
    with pytest.raises(SessionNotFoundError):
        await svc.refresh(issued.refresh_token)


async def test_session_refresh_expired() -> None:
    store = FakeSessionStore()
    past = [_dt.datetime.now(_dt.UTC) - _dt.timedelta(days=400)]
    svc = SessionService(store, clock=lambda: past[0])
    issued = await svc.start(uuid.uuid4())
    past[0] = _dt.datetime.now(_dt.UTC)
    with pytest.raises(SessionExpiredError):
        await svc.refresh(issued.refresh_token)


# --- endpoint flow (real DB) -------------------------------------------


@pytest.fixture
async def seeded_user(db: object) -> AsyncIterator[tuple[AsyncSession, str, str]]:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User

    session = db  # type: ignore[assignment]
    assert isinstance(session, AsyncSession)
    user = User(display_name="Alice Operator", status="active")
    session.add(user)
    await session.flush()
    ident = AuthIdentity(user_id=user.id, provider="local", subject="alice")
    session.add(ident)
    await session.flush()
    session.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    await session.commit()
    yield session, "alice", "Wolke7-Bahnhof!x"


async def test_login_me_logout_flow(
    client: httpx.AsyncClient, seeded_user: tuple[AsyncSession, str, str]
) -> None:
    _, username, password = seeded_user

    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["display_name"] == "Alice Operator"
    csrf = body["csrf_token"]
    assert client.cookies.get("bbz_access") and client.cookies.get("bbz_refresh")

    me = await client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["display_name"] == "Alice Operator"
    assert me.json()["permissions"] == []

    # logout without the CSRF header -> 403
    assert (await client.post("/api/v1/auth/logout")).status_code == 403
    ok = await client.post("/api/v1/auth/logout", headers={"x-csrf-token": csrf})
    assert ok.status_code == 204

    # session is revoked server-side: the (still-present) access token is rejected
    client.cookies.set("bbz_access", body_access := r.cookies["bbz_access"])
    assert body_access
    me2 = await client.get("/api/v1/auth/me", headers={"authorization": f"Bearer {body_access}"})
    assert me2.status_code == 401


async def test_login_bad_password_is_401(
    client: httpx.AsyncClient, seeded_user: tuple[AsyncSession, str, str]
) -> None:
    r = await client.post("/api/v1/auth/login", json={"username": "alice", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_me_requires_auth(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/auth/me")
    assert r.status_code == 401
    r2 = await client.get("/api/v1/auth/me", headers={"authorization": "Bearer garbage"})
    assert r2.status_code == 401
