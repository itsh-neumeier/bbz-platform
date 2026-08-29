"""TOTP: unit verification + enrol/activate/login/recovery flow."""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "totp-test-secret-at-least-32-bytes-long!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_TOTP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    os.environ.pop("BBZ_TOTP_ENCRYPTION_KEY", None)


def test_verify_code_window_and_reuse() -> None:
    from bbz_core.auth.totp import new_secret, verify_code

    secret = new_secret()
    now = time.time()
    code = pyotp.TOTP(secret).at(now)
    step = verify_code(secret, code, now=now)
    assert step is not None
    # same code again with last_step set -> rejected (replay)
    assert verify_code(secret, code, now=now, last_step=step) is None
    assert verify_code(secret, "000000", now=now) is None


def test_encrypt_roundtrip() -> None:
    from bbz_core.auth.totp import decrypt_secret, encrypt_secret

    assert decrypt_secret(encrypt_secret("JBSWY3DPEHPK3PXP")) == "JBSWY3DPEHPK3PXP"


async def _mk_user(s: AsyncSession, username: str) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
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


async def test_enrol_activate_then_login_requires_totp(env: tuple) -> None:
    client, s = env
    await _mk_user(s, "alice")
    await client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "Wolke7-Bahnhof!x"}
    )

    enrol = (await client.post("/api/v1/auth/totp/enrol")).json()
    secret = enrol["secret"]
    assert enrol["otpauth_uri"].startswith("otpauth://totp/")
    assert len(enrol["recovery_codes"]) == 10

    code = pyotp.TOTP(secret).now()
    assert (await client.post("/api/v1/auth/totp/activate", json={"code": code})).status_code == 204

    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with fresh:
        no_totp = await fresh.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "Wolke7-Bahnhof!x"}
        )
        assert no_totp.status_code == 401
        assert no_totp.json()["error"]["code"] == "totp_required"

        bad = await fresh.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "Wolke7-Bahnhof!x", "totp": "000000"},
        )
        assert bad.status_code == 401

        # the exact code of the next 30s window: not the one /activate consumed,
        # and still inside the server's +-1 step verification window.
        next_window = (int(time.time() // 30) + 1) * 30 + 5
        good = await fresh.post(
            "/api/v1/auth/login",
            json={
                "username": "alice",
                "password": "Wolke7-Bahnhof!x",
                "totp": pyotp.TOTP(secret).at(next_window),
            },
        )
        assert good.status_code == 200


async def test_recovery_code_logs_in_once(env: tuple) -> None:
    client, s = env
    await _mk_user(s, "bob")
    await client.post(
        "/api/v1/auth/login", json={"username": "bob", "password": "Wolke7-Bahnhof!x"}
    )
    enrol = (await client.post("/api/v1/auth/totp/enrol")).json()
    await client.post(
        "/api/v1/auth/totp/activate", json={"code": pyotp.TOTP(enrol["secret"]).now()}
    )
    recovery = enrol["recovery_codes"][0]

    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with fresh:
        first = await fresh.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": "Wolke7-Bahnhof!x", "totp": recovery},
        )
        assert first.status_code == 200
        second = await fresh.post(
            "/api/v1/auth/login",
            json={"username": "bob", "password": "Wolke7-Bahnhof!x", "totp": recovery},
        )
        assert second.status_code == 401  # single-use


async def test_disable_totp_removes_requirement(env: tuple) -> None:
    client, s = env
    await _mk_user(s, "carl")
    await client.post(
        "/api/v1/auth/login", json={"username": "carl", "password": "Wolke7-Bahnhof!x"}
    )
    enrol = (await client.post("/api/v1/auth/totp/enrol")).json()
    await client.post(
        "/api/v1/auth/totp/activate", json={"code": pyotp.TOTP(enrol["secret"]).now()}
    )
    assert (await client.delete("/api/v1/auth/totp")).status_code == 204

    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with fresh:
        r = await fresh.post(
            "/api/v1/auth/login", json={"username": "carl", "password": "Wolke7-Bahnhof!x"}
        )
        assert r.status_code == 200
