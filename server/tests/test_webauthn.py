"""WebAuthn / FIDO2 as a second factor for local accounts (roadmap E21-06).

Drives the ceremonies with an in-process software authenticator (a P-256
keypair + a hand-built attestation / assertion), so no browser / CDP is needed.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from collections.abc import AsyncIterator, Iterator

import cbor2
import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import bytes_to_base64url

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
from bbz_core.infra.models.mfa_policy import MfaPolicy
from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole
from bbz_core.infra.models.webauthn import WebauthnCredential

_PW = "Wolke7-Bahnhof!x"
_RP_ID = "bbz.test"
_ORIGIN = "https://bbz.test"


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ.update(
        {
            "BBZ_ARGON2_MEMORY_COST_KIB": "512",
            "BBZ_ARGON2_TIME_COST": "1",
            "BBZ_JWT_SECRET": "webauthn-test-secret-at-least-32-bytes!!",
            "BBZ_SESSION_COOKIE_SECURE": "false",
            "BBZ_WEBAUTHN_RP_ID": _RP_ID,
            "BBZ_WEBAUTHN_ORIGINS": _ORIGIN,
        }
    )
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    for k in (
        "BBZ_WEBAUTHN_RP_ID",
        "BBZ_WEBAUTHN_ORIGINS",
        "BBZ_MFA_STEPUP_PERMISSIONS",
    ):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


# --- a minimal software authenticator -----------------------------------


class SoftKey:
    def __init__(self, *, uv: bool = True) -> None:
        self._priv = ec.generate_private_key(SECP256R1())
        self.credential_id = secrets.token_bytes(20)
        self.sign_count = 0
        self._uv = uv

    def _auth_data(self, *, attested: bool) -> bytes:
        rp_hash = hashlib.sha256(_RP_ID.encode()).digest()
        flags = 0x01 | (0x04 if self._uv else 0x00) | (0x40 if attested else 0x00)
        self.sign_count += 1
        out = rp_hash + bytes([flags]) + self.sign_count.to_bytes(4, "big")
        if attested:
            nums = self._priv.public_key().public_numbers()
            cose = cbor2.dumps(
                {
                    1: 2,
                    3: -7,
                    -1: 1,
                    -2: nums.x.to_bytes(32, "big"),
                    -3: nums.y.to_bytes(32, "big"),
                }
            )
            out += b"\x00" * 16  # aaguid
            out += len(self.credential_id).to_bytes(2, "big") + self.credential_id + cose
        return out

    def _client_data(self, kind: str, challenge_b64: str) -> bytes:
        return json.dumps(
            {"type": kind, "challenge": challenge_b64, "origin": _ORIGIN, "crossOrigin": False}
        ).encode()

    def register(self, options_json: str) -> str:
        opts = json.loads(options_json)
        client_data = self._client_data("webauthn.create", opts["challenge"])
        att_obj = cbor2.dumps(
            {"fmt": "none", "attStmt": {}, "authData": self._auth_data(attested=True)}
        )
        return json.dumps(
            {
                "id": bytes_to_base64url(self.credential_id),
                "rawId": bytes_to_base64url(self.credential_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": bytes_to_base64url(client_data),
                    "attestationObject": bytes_to_base64url(att_obj),
                    "transports": ["internal"],
                },
                "clientExtensionResults": {},
            }
        )

    def authenticate(self, options_json: str) -> str:
        opts = json.loads(options_json)
        client_data = self._client_data("webauthn.get", opts["challenge"])
        auth_data = self._auth_data(attested=False)
        sig = self._priv.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return json.dumps(
            {
                "id": bytes_to_base64url(self.credential_id),
                "rawId": bytes_to_base64url(self.credential_id),
                "type": "public-key",
                "response": {
                    "clientDataJSON": bytes_to_base64url(client_data),
                    "authenticatorData": bytes_to_base64url(auth_data),
                    "signature": bytes_to_base64url(sig),
                    "userHandle": None,
                },
                "clientExtensionResults": {},
            }
        )


# --- helpers -----------------------------------------------------------


async def _user(s: AsyncSession, username: str, *, roles: list[str] | None = None) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password

    await s.rollback()
    async with s.begin():
        u = User(display_name=username.title())
        s.add(u)
        await s.flush()
        ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
        s.add(ident)
        await s.flush()
        s.add(LocalCredential(auth_identity_id=ident.id, password_hash=hash_password(_PW)))
        for key in roles or []:
            r = (await s.execute(select(Role).where(Role.key == key))).scalar_one_or_none()
            if r is None:
                r = Role(key=key, name=key.title())
                s.add(r)
                await s.flush()
            s.add(UserRole(user_id=u.id, role_id=r.id))
        return u.id


async def _admin(s: AsyncSession, perms: list[str]) -> None:
    from bbz_core.auth.hashing import hash_password

    await s.rollback()
    async with s.begin():
        u = User(display_name="Admin")
        s.add(u)
        await s.flush()
        ident = AuthIdentity(user_id=u.id, provider="local", subject="admin")
        s.add(ident)
        await s.flush()
        s.add(LocalCredential(auth_identity_id=ident.id, password_hash=hash_password(_PW)))
        role = Role(key="r-admin", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))


async def _login(c: httpx.AsyncClient, username: str, **extra: str) -> httpx.Response:
    return await c.post("/api/v1/auth/login", json={"username": username, "password": _PW, **extra})


def _fresh(c: httpx.AsyncClient) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=c._transport, base_url="http://testserver")  # type: ignore[attr-defined]


async def _register_key(c: httpx.AsyncClient, *, name: str = "yubikey") -> SoftKey:
    key = SoftKey()
    opts = (await c.post("/api/v1/auth/webauthn/register/options")).json()["options"]
    r = await c.post(
        "/api/v1/auth/webauthn/register/verify",
        json={"response": key.register(opts), "name": name},
    )
    assert r.status_code == 201, r.text
    return key


# --- registration ----------------------------------------------------


async def test_register_and_list_a_credential(env: tuple) -> None:
    c, s = env
    await _user(s, "alice")
    await _login(c, "alice")
    await _register_key(c, name="Alice's key")

    listed = (await c.get("/api/v1/auth/webauthn/credentials")).json()["credentials"]
    assert len(listed) == 1 and listed[0]["name"] == "Alice's key"
    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "WEBAUTHN_REGISTERED")
        )
    ).scalar_one()
    assert n == 1


async def test_registration_rejects_a_tampered_origin(env: tuple) -> None:
    c, s = env
    await _user(s, "mallory")
    await _login(c, "mallory")
    key = SoftKey()
    opts = (await c.post("/api/v1/auth/webauthn/register/options")).json()["options"]
    resp = json.loads(key.register(opts))
    resp["response"]["clientDataJSON"] = bytes_to_base64url(
        json.dumps(
            {
                "type": "webauthn.create",
                "challenge": json.loads(opts)["challenge"],
                "origin": "https://evil.test",
            }
        ).encode()
    )
    r = await c.post("/api/v1/auth/webauthn/register/verify", json={"response": json.dumps(resp)})
    assert r.status_code == 422


async def test_credentials_are_isolated_per_user(env: tuple) -> None:
    c, s = env
    await _user(s, "u1")
    await _user(s, "u2")
    await _login(c, "u1")
    await _register_key(c)

    async with _fresh(c) as c2:
        await _login(c2, "u2")
        assert (await c2.get("/api/v1/auth/webauthn/credentials")).json()["credentials"] == []


async def test_webauthn_disabled_when_unconfigured(env: tuple) -> None:
    c, s = env
    os.environ.pop("BBZ_WEBAUTHN_RP_ID", None)
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    await _user(s, "hank")
    await _login(c, "hank")
    assert (await c.post("/api/v1/auth/webauthn/register/options")).status_code == 503


# --- login as a second factor --------------------------------------


async def test_login_challenges_and_verifies_webauthn(env: tuple) -> None:
    c, s = env
    await _user(s, "bob")
    await _login(c, "bob")
    key = await _register_key(c)

    async with _fresh(c) as fresh:
        challenge = await _login(fresh, "bob")
        assert challenge.status_code == 401
        err = challenge.json()["error"]
        assert err["code"] == "webauthn_required"

        ok = await _login(fresh, "bob", webauthn=key.authenticate(err["details"]["options"]))
        assert ok.status_code == 200 and ok.cookies.get("bbz_access")


async def test_a_bad_assertion_is_rejected(env: tuple) -> None:
    c, s = env
    await _user(s, "carol")
    await _login(c, "carol")
    key = await _register_key(c)

    async with _fresh(c) as fresh:
        options = (await _login(fresh, "carol")).json()["error"]["details"]["options"]
        forger = SoftKey()
        forger.credential_id = key.credential_id  # right id, wrong key
        r = await _login(fresh, "carol", webauthn=forger.authenticate(options))
        assert r.status_code == 401


async def test_sign_count_moves_forward(env: tuple) -> None:
    c, s = env
    uid = await _user(s, "dave")
    await _login(c, "dave")
    key = await _register_key(c)

    for _ in range(2):
        async with _fresh(c) as fresh:
            options = (await _login(fresh, "dave")).json()["error"]["details"]["options"]
            r = await _login(fresh, "dave", webauthn=key.authenticate(options))
            assert r.status_code == 200

    await s.rollback()
    cred = (
        await s.execute(
            select(WebauthnCredential)
            .join(AuthIdentity, AuthIdentity.id == WebauthnCredential.auth_identity_id)
            .where(AuthIdentity.user_id == uid)
        )
    ).scalar_one()
    assert cred.sign_count >= 2


async def test_challenge_is_single_use(env: tuple) -> None:
    c, s = env
    await _user(s, "grace")
    await _login(c, "grace")
    key = await _register_key(c)

    async with _fresh(c) as fresh:
        options = (await _login(fresh, "grace")).json()["error"]["details"]["options"]
        assert (await _login(fresh, "grace", webauthn=key.authenticate(options))).status_code == 200
        replay = await _login(fresh, "grace", webauthn=key.authenticate(options))
        assert replay.status_code == 401


# --- MFA policy + step-up integration -----------------------------


async def test_a_passkey_satisfies_the_role_mfa_policy(env: tuple) -> None:
    c, s = env
    await _user(s, "erin", roles=["leitung"])
    await _login(c, "erin")  # in grace (default 7d after adding the policy)
    key = await _register_key(c)
    await s.rollback()
    async with s.begin():
        s.add(MfaPolicy(role_key="leitung", grace_period_days=0))  # enforce now

    async with _fresh(c) as fresh:
        # not blocked (has a factor) — challenged instead
        challenge = await _login(fresh, "erin")
        assert challenge.status_code == 401
        assert challenge.json()["error"]["code"] == "webauthn_required"
        options = challenge.json()["error"]["details"]["options"]
        assert (await _login(fresh, "erin", webauthn=key.authenticate(options))).status_code == 200


async def test_stepup_accepts_a_webauthn_assertion(env: tuple) -> None:
    c, s = env
    os.environ["BBZ_MFA_STEPUP_PERMISSIONS"] = '["permissions.manage"]'
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    await _admin(s, ["permissions.manage"])
    await s.rollback()
    async with s.begin():
        s.add(Role(key="leitung", name="Leitung"))
    await _login(c, "admin")
    key = await _register_key(c)

    blocked = await c.put("/api/v1/auth/mfa-policies/leitung", json={"grace_period_days": 2})
    assert blocked.status_code == 401 and blocked.json()["error"]["code"] == "step_up_required"

    options = (await c.post("/api/v1/auth/webauthn/authenticate/options")).json()["options"]
    su = await c.post(
        "/api/v1/auth/mfa-policies/step-up", json={"webauthn": key.authenticate(options)}
    )
    assert su.status_code == 204
    ok = await c.put("/api/v1/auth/mfa-policies/leitung", json={"grace_period_days": 2})
    assert ok.status_code == 200


# --- removal ------------------------------------------------------


async def test_remove_a_credential(env: tuple) -> None:
    c, s = env
    await _user(s, "frank")
    await _login(c, "frank")
    await _register_key(c)
    await _register_key(c, name="backup")

    creds = (await c.get("/api/v1/auth/webauthn/credentials")).json()["credentials"]
    assert len(creds) == 2
    d = await c.delete(f"/api/v1/auth/webauthn/credentials/{creds[0]['id']}")
    assert d.status_code == 204
    assert len((await c.get("/api/v1/auth/webauthn/credentials")).json()["credentials"]) == 1

    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "WEBAUTHN_REMOVED")
        )
    ).scalar_one()
    assert n == 1
