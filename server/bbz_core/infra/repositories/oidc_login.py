"""OIDC login orchestration (roadmap E21-01).

Holds the per-attempt secrets in ``oidc_login_flows`` (DB-backed for HA), runs
the two IdP round trips through :mod:`bbz_core.auth.oidc`, validates the ID
token, maps the ``sub`` claim to a BBZ user, and audits the outcome. Minting the
session is the API's job (it owns the cookies).

Local logins are unaffected — this is an additional provider.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import time
import uuid
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.auth.oidc import (
    OidcConfig,
    OidcError,
    OidcMetadata,
    OidcStateError,
    exchange,
    fetch_jwks,
    fetch_metadata,
    start,
    validate_id_token,
)
from bbz_core.auth.oidc.http import OidcHttp, UrllibOidcHttp
from bbz_core.auth.oidc.idtoken import IdTokenClaims
from bbz_core.infra.models.identity import AuthIdentity, User
from bbz_core.infra.models.oidc import OidcLoginFlow
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)

#: metadata is stable; cache the discovery per issuer for a few minutes
_META_CACHE: dict[str, tuple[float, OidcMetadata]] = {}
_META_TTL = 300.0


class OidcProviderNotConfigured(OidcError):
    """The requested OIDC provider has no issuer / client_id configured."""


class OidcUserNotProvisioned(OidcError):
    """The IdP principal has no BBZ user and JIT provisioning is off."""


@dataclass(frozen=True)
class _ConsumedFlow:
    nonce: str
    code_verifier_enc: str


def _fernet() -> Fernet:
    digest = hashlib.sha256(get_settings().jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def config_for(provider: str) -> OidcConfig:
    s = get_settings()
    if provider == "entra_oidc":
        if not s.oidc_entra_issuer or not s.oidc_entra_client_id:
            raise OidcProviderNotConfigured("entra_oidc issuer / client_id not set")
        return OidcConfig(
            provider="entra_oidc",
            issuer=s.oidc_entra_issuer,
            client_id=s.oidc_entra_client_id,
            client_secret=s.oidc_entra_client_secret or None,
            redirect_uri=s.oidc_entra_redirect_uri,
        )
    raise OidcProviderNotConfigured(f"unknown OIDC provider {provider!r}")


class OidcLoginService:
    def __init__(self, session: AsyncSession, *, http: OidcHttp | None = None) -> None:
        self._s = session
        self._http = http or UrllibOidcHttp()

    async def _metadata(self, cfg: OidcConfig) -> OidcMetadata:
        hit = _META_CACHE.get(cfg.issuer)
        if hit and time.monotonic() - hit[0] < _META_TTL:
            return hit[1]
        meta = await fetch_metadata(cfg, self._http)
        _META_CACHE[cfg.issuer] = (time.monotonic(), meta)
        return meta

    async def begin(self, provider: str) -> str:
        """Persist a new login attempt and return the IdP authorization URL."""
        cfg = config_for(provider)
        meta = await self._metadata(cfg)
        flow = start(cfg, meta)
        ttl = get_settings().oidc_login_flow_ttl_seconds
        await self._s.rollback()
        async with self._s.begin():
            self._s.add(
                OidcLoginFlow(
                    state=flow.state,
                    provider=provider,
                    nonce=flow.nonce,
                    code_verifier_enc=_fernet().encrypt(flow.code_verifier.encode()).decode(),
                    redirect_uri=cfg.redirect_uri,
                    created_at=_now(),
                    expires_at=_now() + _dt.timedelta(seconds=ttl),
                )
            )
        return flow.authorization_url

    async def complete(
        self,
        provider: str,
        *,
        code: str,
        state: str,
        client_id: str | None = None,
        workplace_id: str | None = None,
    ) -> uuid.UUID:
        """Consume the ``state`` row, finish the flow, return the BBZ ``user_id``.
        Audits ``LOGIN_SUCCEEDED`` / ``LOGIN_FAILED`` either way."""
        try:
            consumed = await self._consume_flow(provider, state)
            user_id = await self._finish(provider, consumed, code=code)
        except OidcError as exc:
            await self._audit_failed(provider, reason=type(exc).__name__, client_id=client_id)
            raise
        await self._audit_ok(user_id, provider, client_id=client_id, workplace_id=workplace_id)
        return user_id

    # --- steps ----------------------------------------------------

    async def _consume_flow(self, provider: str, state: str) -> _ConsumedFlow:
        await self._s.rollback()
        row = await self._s.get(OidcLoginFlow, state)
        if row is None or row.provider != provider:
            raise OidcStateError("unknown or foreign login state")
        consumed = _ConsumedFlow(nonce=row.nonce, code_verifier_enc=row.code_verifier_enc)
        expired = row.expires_at < _now()
        await self._s.rollback()
        async with self._s.begin():  # single-use: the row is gone before anything else
            await self._s.execute(delete(OidcLoginFlow).where(OidcLoginFlow.state == state))
        if expired:
            raise OidcStateError("login state expired")
        return consumed

    async def _finish(self, provider: str, flow: _ConsumedFlow, *, code: str) -> uuid.UUID:
        cfg = config_for(provider)
        meta = await self._metadata(cfg)
        try:
            verifier = _fernet().decrypt(flow.code_verifier_enc.encode()).decode()
        except InvalidToken as exc:
            raise OidcStateError("login state is corrupt") from exc

        tokens = await exchange(cfg, meta, code=code, code_verifier=verifier, http=self._http)
        jwks = await fetch_jwks(meta, self._http)
        claims = validate_id_token(tokens.id_token, cfg=cfg, meta=meta, jwks=jwks, nonce=flow.nonce)
        return await self._resolve_user(provider, claims)

    async def _resolve_user(self, provider: str, claims: IdTokenClaims) -> uuid.UUID:
        await self._s.rollback()
        existing = (
            await self._s.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == provider, AuthIdentity.subject == claims.subject
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.user_id

        if not get_settings().oidc_jit_provisioning:
            raise OidcUserNotProvisioned(claims.subject)

        await self._s.rollback()  # close the read tx from the lookup above
        async with self._s.begin():
            user = User(display_name=claims.name or claims.preferred_username or claims.email or "")
            self._s.add(user)
            await self._s.flush()
            self._s.add(AuthIdentity(user_id=user.id, provider=provider, subject=claims.subject))
        return user.id

    # --- audit ---------------------------------------------------

    async def _audit_ok(
        self,
        user_id: uuid.UUID,
        provider: str,
        *,
        client_id: str | None,
        workplace_id: str | None,
    ) -> None:
        await self._s.rollback()
        async with self._s.begin():
            await AuditService(self._s).write(
                AuditAction.LOGIN_SUCCEEDED,
                actor_user_id=user_id,
                actor_client_id=client_id,
                workplace_id=workplace_id,
                target_type="login_attempt",
                after={"provider": provider},
            )

    async def _audit_failed(self, provider: str, *, reason: str, client_id: str | None) -> None:
        await self._s.rollback()
        async with self._s.begin():
            await AuditService(self._s).write(
                AuditAction.LOGIN_FAILED,
                actor_client_id=client_id,
                target_type="login_attempt",
                after={"provider": provider, "reason": reason},
            )
