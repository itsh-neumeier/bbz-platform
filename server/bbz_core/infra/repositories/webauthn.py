"""WebAuthn / FIDO2 registration + assertion orchestration (roadmap E21-06).

Wraps ``py_webauthn`` (the ceremony crypto) with the BBZ credential + challenge
storage. WebAuthn is a **second factor for local accounts**: a credential hangs
off the ``local`` auth identity, and an assertion satisfies the same MFA-policy
check as a TOTP code (E21-05). Passwordless first-factor is out of scope.
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid
from dataclasses import dataclass

import webauthn
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    UserVerificationRequirement,
)

from bbz_core.audit import AuditAction, AuditWriter
from bbz_core.infra.models.identity import AuthIdentity
from bbz_core.infra.models.webauthn import WebauthnChallenge, WebauthnCredential
from bbz_core.settings import get_settings


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class WebauthnError(Exception):
    pass


class WebauthnNotConfigured(WebauthnError):
    """``webauthn_rp_id`` / ``webauthn_origins`` unset — enrolment unavailable."""


class NoLocalIdentity(WebauthnError):
    pass


class ChallengeExpired(WebauthnError):
    pass


class CredentialNotFound(WebauthnError):
    pass


@dataclass(frozen=True)
class _Cfg:
    rp_id: str
    rp_name: str
    origins: list[str]
    require_uv: bool
    ttl: int


def _cfg() -> _Cfg:
    s = get_settings()
    origins = [o.strip() for o in s.webauthn_origins.split(",") if o.strip()]
    if not s.webauthn_rp_id or not origins:
        raise WebauthnNotConfigured("webauthn_rp_id / webauthn_origins are not set")
    return _Cfg(
        rp_id=s.webauthn_rp_id,
        rp_name=s.webauthn_rp_name,
        origins=origins,
        require_uv=s.webauthn_require_user_verification,
        ttl=s.webauthn_challenge_ttl_seconds,
    )


@dataclass(frozen=True)
class CredentialView:
    id: uuid.UUID
    name: str
    aaguid: str
    transports: list[str]
    created_at: _dt.datetime
    last_used_at: _dt.datetime | None


def _view(c: WebauthnCredential) -> CredentialView:
    return CredentialView(
        id=c.id,
        name=c.name,
        aaguid=c.aaguid,
        transports=[t for t in c.transports.split(",") if t],
        created_at=c.created_at,
        last_used_at=c.last_used_at,
    )


class WebauthnService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- registration ------------------------------------------------

    async def begin_registration(
        self, auth_identity_id: uuid.UUID, *, user_name: str, user_display_name: str
    ) -> str:
        cfg = _cfg()
        await self._s.rollback()
        existing = (
            await self._s.execute(
                select(WebauthnCredential.credential_id).where(
                    WebauthnCredential.auth_identity_id == auth_identity_id
                )
            )
        ).scalars()
        opts = webauthn.generate_registration_options(
            rp_id=cfg.rp_id,
            rp_name=cfg.rp_name,
            user_id=auth_identity_id.bytes,
            user_name=user_name,
            user_display_name=user_display_name,
            exclude_credentials=[PublicKeyCredentialDescriptor(id=cid) for cid in existing],
            authenticator_selection=AuthenticatorSelectionCriteria(
                user_verification=UserVerificationRequirement.REQUIRED
                if cfg.require_uv
                else UserVerificationRequirement.PREFERRED,
                resident_key=None,
            ),
        )
        await self._stash(opts.challenge, kind="register", auth_identity_id=auth_identity_id)
        return str(webauthn.options_to_json(opts))

    async def complete_registration(
        self, auth_identity_id: uuid.UUID, *, response: str, name: str, actor_id: uuid.UUID
    ) -> CredentialView:
        cfg = _cfg()
        challenge = await self._consume(kind="register", auth_identity_id=auth_identity_id)
        try:
            v = webauthn.verify_registration_response(
                credential=response,
                expected_challenge=challenge,
                expected_rp_id=cfg.rp_id,
                expected_origin=cfg.origins,
                require_user_verification=cfg.require_uv,
            )
        except Exception as exc:  # any py_webauthn failure → a clean 4xx
            raise WebauthnError(f"registration could not be verified: {exc}") from exc

        transports = _transports_from(response)
        await self._s.rollback()
        async with self._s.begin():
            cred = WebauthnCredential(
                auth_identity_id=auth_identity_id,
                credential_id=v.credential_id,
                public_key=v.credential_public_key,
                sign_count=v.sign_count,
                transports=",".join(transports),
                aaguid=str(v.aaguid or ""),
                name=name.strip()[:80] or "security key",
            )
            self._s.add(cred)
            await self._s.flush()
            await AuditWriter(self._s).record(
                AuditAction.WEBAUTHN_REGISTERED,
                actor_user_id=actor_id,
                target_type="webauthn_credential",
                target_id=str(cred.id),
                commit=False,
            )
        return _view(cred)

    # --- authentication (a login factor) --------------------------

    async def begin_authentication(self, user_id: uuid.UUID) -> str:
        cfg = _cfg()
        creds = await self._creds_for_user(user_id)
        if not creds:
            raise CredentialNotFound("no WebAuthn credential for this account")
        opts = webauthn.generate_authentication_options(
            rp_id=cfg.rp_id,
            allow_credentials=[
                PublicKeyCredentialDescriptor(
                    id=c.credential_id,
                    transports=[
                        AuthenticatorTransport(t)
                        for t in c.transports.split(",")
                        if t in AuthenticatorTransport._value2member_map_
                    ]
                    or None,
                )
                for c in creds
            ],
            user_verification=UserVerificationRequirement.REQUIRED
            if cfg.require_uv
            else UserVerificationRequirement.PREFERRED,
        )
        await self._stash(opts.challenge, kind="authenticate", user_id=user_id)
        return str(webauthn.options_to_json(opts))

    async def verify_authentication(self, user_id: uuid.UUID, *, response: str) -> bool:
        cfg = _cfg()
        try:
            challenge = await self._consume(kind="authenticate", user_id=user_id)
        except (ChallengeExpired, CredentialNotFound):
            return False
        try:
            raw_id = base64url_to_bytes(json.loads(response)["rawId"])
        except (ValueError, KeyError, TypeError):
            return False
        creds = await self._creds_for_user(user_id)
        cred = next((c for c in creds if c.credential_id == raw_id), None)
        if cred is None:
            return False
        cred_pk, pub_key, cur_count = cred.id, cred.public_key, cred.sign_count
        try:
            v = webauthn.verify_authentication_response(
                credential=response,
                expected_challenge=challenge,
                expected_rp_id=cfg.rp_id,
                expected_origin=cfg.origins,
                credential_public_key=pub_key,
                credential_current_sign_count=cur_count,
                require_user_verification=cfg.require_uv,
            )
        except Exception:
            return False
        new_count = v.new_sign_count
        await self._s.rollback()  # expires `cred` — use the captured primary key
        async with self._s.begin():
            fresh = await self._s.get(WebauthnCredential, cred_pk)
            if fresh is not None:
                fresh.sign_count = new_count
                fresh.last_used_at = _now()
        return True

    async def has_active(self, user_id: uuid.UUID) -> bool:
        return bool(await self._creds_for_user(user_id))

    # --- CRUD (self-service) -------------------------------------

    async def list_credentials(self, auth_identity_id: uuid.UUID) -> list[CredentialView]:
        await self._s.rollback()
        rows = (
            await self._s.execute(
                select(WebauthnCredential)
                .where(WebauthnCredential.auth_identity_id == auth_identity_id)
                .order_by(WebauthnCredential.created_at)
            )
        ).scalars()
        return [_view(c) for c in rows]

    async def remove_credential(
        self, credential_id: uuid.UUID, *, auth_identity_id: uuid.UUID, actor_id: uuid.UUID
    ) -> None:
        await self._s.rollback()
        async with self._s.begin():
            cred = await self._s.get(WebauthnCredential, credential_id)
            if cred is None or cred.auth_identity_id != auth_identity_id:
                raise CredentialNotFound(str(credential_id))
            await self._s.delete(cred)
            await AuditWriter(self._s).record(
                AuditAction.WEBAUTHN_REMOVED,
                actor_user_id=actor_id,
                target_type="webauthn_credential",
                target_id=str(credential_id),
                commit=False,
            )

    # --- helpers ------------------------------------------------

    async def _creds_for_user(self, user_id: uuid.UUID) -> list[WebauthnCredential]:
        await self._s.rollback()
        return list(
            (
                await self._s.execute(
                    select(WebauthnCredential)
                    .join(AuthIdentity, AuthIdentity.id == WebauthnCredential.auth_identity_id)
                    .where(AuthIdentity.user_id == user_id, AuthIdentity.provider == "local")
                )
            ).scalars()
        )

    async def _stash(
        self,
        challenge: bytes,
        *,
        kind: str,
        auth_identity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> None:
        await self._s.rollback()
        async with self._s.begin():
            # one live challenge per (kind, subject) — clear any older one first
            await self._s.execute(
                delete(WebauthnChallenge).where(
                    WebauthnChallenge.kind == kind,
                    WebauthnChallenge.auth_identity_id == auth_identity_id
                    if auth_identity_id is not None
                    else WebauthnChallenge.user_id == user_id,
                )
            )
            self._s.add(
                WebauthnChallenge(
                    kind=kind,
                    auth_identity_id=auth_identity_id,
                    user_id=user_id,
                    challenge=challenge,
                    expires_at=_now() + _dt.timedelta(seconds=_cfg().ttl),
                )
            )

    async def _consume(
        self,
        *,
        kind: str,
        auth_identity_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
    ) -> bytes:
        await self._s.rollback()
        subject = (
            WebauthnChallenge.auth_identity_id == auth_identity_id
            if auth_identity_id is not None
            else WebauthnChallenge.user_id == user_id
        )
        row = (
            await self._s.execute(
                select(WebauthnChallenge).where(WebauthnChallenge.kind == kind, subject)
            )
        ).scalar_one_or_none()
        if row is None:
            raise CredentialNotFound("no pending WebAuthn challenge")
        challenge, expires, row_id = bytes(row.challenge), row.expires_at, row.id
        await self._s.rollback()  # close the read tx before the delete tx
        async with self._s.begin():
            await self._s.execute(delete(WebauthnChallenge).where(WebauthnChallenge.id == row_id))
        if expires < _now():
            raise ChallengeExpired("the WebAuthn challenge has expired")
        return challenge


def _transports_from(response: str) -> list[str]:
    try:
        data = json.loads(response)
        t = data.get("response", {}).get("transports") or []
        return [str(x) for x in t if isinstance(x, str)][:6]
    except (ValueError, AttributeError, TypeError):
        return []
