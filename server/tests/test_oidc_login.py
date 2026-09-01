"""Entra ID / OIDC login (roadmap E21-01): authorization-code + PKCE against a
**mock IdP** (no running server — an RSA keypair + canned discovery/JWKS/token).

Covers the happy path and every negative: forged/replayed ``state``, expired
flow, tampered / wrong-audience / wrong-issuer / expired / bad-nonce / ``alg=none``
ID tokens, an unprovisioned principal, and that local password login still works
alongside.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.auth.oidc import (
    OidcConfig,
    OidcIdTokenInvalid,
    OidcStateError,
    pkce,
    start,
    validate_id_token,
)
from bbz_core.auth.oidc.config import OidcMetadata
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.identity import AuthIdentity, User
from bbz_core.infra.models.oidc import OidcLoginFlow

_ISSUER = "https://idp.test/tenant"
_CLIENT = "bbz-test-client"
_META = OidcMetadata(
    issuer=_ISSUER,
    authorization_endpoint=f"{_ISSUER}/authorize",
    token_endpoint=f"{_ISSUER}/oauth2/token",
    jwks_uri=f"{_ISSUER}/keys",
)
_CFG = OidcConfig(
    provider="entra_oidc",
    issuer=_ISSUER,
    client_id=_CLIENT,
    redirect_uri="https://bbz.local/auth/callback",
)


class _MockIdP:
    def __init__(self, kid: str = "k1") -> None:
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._kid = kid

    def jwks(self) -> list[dict[str, Any]]:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        jwk.update({"kid": self._kid, "use": "sig", "alg": "RS256"})
        return [jwk]

    def id_token(
        self,
        *,
        nonce: str,
        sub: str = "entra-sub-1",
        aud: str = _CLIENT,
        iss: str = _ISSUER,
        expires_in: int = 300,
        alg: str = "RS256",
        key: Any = None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        now = int(time.time())
        claims = {
            "iss": iss,
            "sub": sub,
            "aud": aud,
            "iat": now,
            "exp": now + expires_in,
            "nonce": nonce,
            "email": "op@leitstelle.test",
            "email_verified": True,
            "name": "Test Operator",
            **(extra or {}),
        }
        if alg == "none":
            return jwt.encode(claims, key="", algorithm="none", headers={"kid": self._kid})
        return jwt.encode(claims, key=key or self._key, algorithm=alg, headers={"kid": self._kid})


class _StubHttp:
    def __init__(
        self, idp: _MockIdP | None = None, *, token_error: str | None = None, **_: Any
    ) -> None:
        self._idp = idp or _MockIdP()
        self._token_error = token_error
        self.codes: dict[str, str] = {}  # code -> id_token

    async def get_json(self, url: str) -> dict[str, Any]:
        if url == _CFG.well_known:
            return {
                "issuer": _ISSUER,
                "authorization_endpoint": _META.authorization_endpoint,
                "token_endpoint": _META.token_endpoint,
                "jwks_uri": _META.jwks_uri,
                "id_token_signing_alg_values_supported": ["RS256"],
            }
        if url == _META.jwks_uri:
            return {"keys": self._idp.jwks()}
        raise AssertionError(url)

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        assert url == _META.token_endpoint
        if self._token_error:
            return {"error": self._token_error}
        tok = self.codes.get(data.get("code", ""))
        if tok is None:
            return {"error": "invalid_grant"}
        return {"access_token": "at", "token_type": "Bearer", "id_token": tok}


# --- pure: PKCE + the authorization URL ------------------------------------


def test_pkce_challenge_is_s256_of_the_verifier() -> None:
    import base64
    import hashlib

    v = pkce.new_verifier()
    assert 43 <= len(v) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
    assert pkce.challenge(v) == expected


def test_start_builds_a_code_flow_url_with_state_nonce_and_pkce() -> None:
    flow = start(_CFG, _META)
    q = parse_qs(urlparse(flow.authorization_url).query)
    assert q["response_type"] == ["code"]  # never implicit
    assert q["client_id"] == [_CLIENT]
    assert q["code_challenge_method"] == ["S256"]
    assert q["state"] == [flow.state] and q["nonce"] == [flow.nonce]
    assert q["code_challenge"] == [pkce.challenge(flow.code_verifier)]
    assert "openid" in q["scope"][0]


# --- pure: ID-token validation -------------------------------------------


def _validate(idp: _MockIdP, token: str, *, nonce: str) -> Any:
    return validate_id_token(token, cfg=_CFG, meta=_META, jwks=idp.jwks(), nonce=nonce)


def test_a_well_formed_id_token_validates() -> None:
    idp = _MockIdP()
    claims = _validate(idp, idp.id_token(nonce="n1"), nonce="n1")
    assert claims.subject == "entra-sub-1" and claims.email == "op@leitstelle.test"


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda idp: idp.id_token(nonce="WRONG"), id="bad-nonce"),
        pytest.param(lambda idp: idp.id_token(nonce="n1", aud="someone-else"), id="wrong-aud"),
        pytest.param(lambda idp: idp.id_token(nonce="n1", iss="https://evil.test"), id="wrong-iss"),
        pytest.param(lambda idp: idp.id_token(nonce="n1", expires_in=-120), id="expired"),
        pytest.param(lambda idp: idp.id_token(nonce="n1", alg="none"), id="alg-none"),
    ],
)
def test_bad_id_tokens_are_rejected(make: Any) -> None:
    idp = _MockIdP()
    with pytest.raises(OidcIdTokenInvalid):
        _validate(idp, make(idp), nonce="n1")


def test_a_token_signed_by_a_foreign_key_is_rejected() -> None:
    idp = _MockIdP()
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = idp.id_token(nonce="n1", key=attacker)
    with pytest.raises(OidcIdTokenInvalid):
        _validate(idp, forged, nonce="n1")


# --- integration: begin → callback → session ----------------------------


@pytest.fixture(autouse=True)
def _oidc_env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ.update(
        {
            "BBZ_OIDC_ENTRA_ISSUER": _ISSUER,
            "BBZ_OIDC_ENTRA_CLIENT_ID": _CLIENT,
            "BBZ_OIDC_ENTRA_REDIRECT_URI": _CFG.redirect_uri,
            "BBZ_JWT_SECRET": "oidc-test-secret-at-least-32-bytes-long!!",
            "BBZ_ARGON2_MEMORY_COST_KIB": "512",
            "BBZ_ARGON2_TIME_COST": "1",
            "BBZ_SESSION_COOKIE_SECURE": "false",
        }
    )
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    from bbz_core.infra.repositories import oidc_login as _oidc_mod

    _oidc_mod._META_CACHE.clear()
    yield
    for k in (
        "BBZ_OIDC_ENTRA_ISSUER",
        "BBZ_OIDC_ENTRA_CLIENT_ID",
        "BBZ_OIDC_ENTRA_REDIRECT_URI",
        "BBZ_OIDC_JIT_PROVISIONING",
    ):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _service(s: AsyncSession, idp: _MockIdP, **stub_kw: Any):  # type: ignore[no-untyped-def]
    from bbz_core.infra.repositories.oidc_login import OidcLoginService

    return OidcLoginService(s, http=_StubHttp(idp, **stub_kw))


async def _link_user(s: AsyncSession, subject: str) -> uuid.UUID:
    u = User(display_name="Extern")
    s.add(u)
    await s.flush()
    s.add(AuthIdentity(user_id=u.id, provider="entra_oidc", subject=subject))
    await s.commit()
    return u.id


async def _begin(svc: Any) -> tuple[str, str, str]:
    url = await svc.begin("entra_oidc")
    q = parse_qs(urlparse(url).query)
    return url, q["state"][0], q["nonce"][0]


async def test_full_login_flow_mints_a_user_id_and_audits(s: AsyncSession) -> None:
    idp = _MockIdP()
    uid = await _link_user(s, "entra-sub-1")
    svc = await _service(s, idp)
    _, state, nonce = await _begin(svc)

    code = uuid.uuid4().hex
    svc._http.codes[code] = idp.id_token(nonce=nonce, sub="entra-sub-1")

    got = await svc.complete("entra_oidc", code=code, state=state)
    assert got == uid

    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(OidcLoginFlow))).scalar_one() == 0
    ok = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "LOGIN_SUCCEEDED"))
    ).scalar_one()
    assert ok.after == {"provider": "entra_oidc"}


async def test_a_replayed_callback_finds_no_state(s: AsyncSession) -> None:
    idp = _MockIdP()
    await _link_user(s, "entra-sub-1")
    svc = await _service(s, idp)
    _, state, nonce = await _begin(svc)
    code = uuid.uuid4().hex
    svc._http.codes[code] = idp.id_token(nonce=nonce)
    await svc.complete("entra_oidc", code=code, state=state)

    with pytest.raises(OidcStateError):
        await svc.complete("entra_oidc", code=code, state=state)


async def test_an_unknown_state_is_rejected(s: AsyncSession) -> None:
    svc = await _service(s, _MockIdP())
    with pytest.raises(OidcStateError):
        await svc.complete("entra_oidc", code="x", state="never-issued")
    await s.rollback()
    assert (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGIN_FAILED")
        )
    ).scalar_one() == 1


async def test_an_expired_flow_row_is_rejected(s: AsyncSession) -> None:
    import datetime as _dt

    idp = _MockIdP()
    svc = await _service(s, idp)
    _, state, _nonce = await _begin(svc)
    await s.rollback()
    async with s.begin():
        row = await s.get(OidcLoginFlow, state)
        assert row is not None
        row.expires_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(minutes=1)
    with pytest.raises(OidcStateError):
        await svc.complete("entra_oidc", code="x", state=state)


async def test_a_tampered_id_token_fails_the_callback(s: AsyncSession) -> None:
    idp = _MockIdP()
    await _link_user(s, "entra-sub-1")
    svc = await _service(s, idp)
    _, state, _nonce = await _begin(svc)
    code = uuid.uuid4().hex
    svc._http.codes[code] = idp.id_token(nonce="a-different-nonce")  # nonce won't match
    with pytest.raises(OidcIdTokenInvalid):
        await svc.complete("entra_oidc", code=code, state=state)


async def test_an_unprovisioned_principal_is_refused_unless_jit_is_on(s: AsyncSession) -> None:
    from bbz_core import settings as settings_mod
    from bbz_core.infra.repositories.oidc_login import OidcUserNotProvisioned

    idp = _MockIdP()
    svc = await _service(s, idp)
    _, state, nonce = await _begin(svc)
    code = uuid.uuid4().hex
    svc._http.codes[code] = idp.id_token(nonce=nonce, sub="brand-new")
    with pytest.raises(OidcUserNotProvisioned):
        await svc.complete("entra_oidc", code=code, state=state)

    # turn JIT on → the same principal is created
    os.environ["BBZ_OIDC_JIT_PROVISIONING"] = "true"
    settings_mod.get_settings.cache_clear()
    svc2 = await _service(s, idp)
    _, state2, nonce2 = await _begin(svc2)
    code2 = uuid.uuid4().hex
    svc2._http.codes[code2] = idp.id_token(nonce=nonce2, sub="brand-new")
    uid = await svc2.complete("entra_oidc", code=code2, state=state2)
    await s.rollback()
    ident = (
        await s.execute(select(AuthIdentity).where(AuthIdentity.subject == "brand-new"))
    ).scalar_one()
    assert ident.user_id == uid


async def test_the_state_row_survives_a_node_change(s: AsyncSession) -> None:
    """begin() on one service instance, complete() on another — the flow is
    DB-backed, not in-memory (HA)."""
    idp = _MockIdP()
    await _link_user(s, "entra-sub-1")
    begin_svc = await _service(s, idp)
    _, state, nonce = await _begin(begin_svc)

    complete_svc = await _service(s, idp)  # a "different node"
    code = uuid.uuid4().hex
    complete_svc._http.codes[code] = idp.id_token(nonce=nonce)
    assert await complete_svc.complete("entra_oidc", code=code, state=state)


# --- the API surface + local login still works -------------------------


@pytest.fixture
def _stub_endpoint_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API endpoints build their own ``UrllibOidcHttp`` — swap it for a stub
    so the tests never touch the network."""
    from bbz_core.infra.repositories import oidc_login as mod

    monkeypatch.setattr(mod, "UrllibOidcHttp", _StubHttp)


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object, _stub_endpoint_http: None
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def test_oidc_start_endpoint_returns_an_authorization_url(env: tuple) -> None:
    client, _ = env
    r = await client.get("/api/v1/auth/oidc/entra_oidc/start")
    assert r.status_code == 200
    url = r.json()["authorization_url"]
    assert url.startswith(f"{_ISSUER}/authorize?") and "code_challenge_method=S256" in url


async def test_oidc_start_for_an_unknown_provider_is_404(env: tuple) -> None:
    client, _ = env
    assert (await client.get("/api/v1/auth/oidc/nope/start")).status_code == 404


async def test_local_password_login_is_unaffected(env: tuple) -> None:
    client, s = env
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User

    u = User(display_name="Local")
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject="localuser")
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    await s.commit()

    r = await client.post(
        "/api/v1/auth/login", json={"username": "localuser", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200 and r.cookies.get("bbz_access")
