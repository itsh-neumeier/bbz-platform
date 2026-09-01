"""Interactive authentication endpoints: login / refresh / logout / me.

Cookie-based for the web/kiosk clients (HttpOnly access + refresh, plus a
readable double-submit CSRF token). Bearer tokens also work for agents.
Effective permissions on ``/me`` come from the permission service (E02-08).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.deps import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    AuthContext,
    current_auth,
    db_session,
    require_csrf,
)
from bbz_core.api.errors import (
    MfaRequiredError,
    NotFoundError,
    ServiceUnavailableError,
    TotpRequiredError,
    UnauthorizedError,
    WebauthnRequiredError,
)
from bbz_core.audit import AuditAction, AuditWriter
from bbz_core.auth.local import LocalAuthResult
from bbz_core.auth.mfa import ChallengeResult, TotpService
from bbz_core.auth.registry import AuthProviderRegistry
from bbz_core.auth.sessions import (
    SessionExpiredError,
    SessionNotFoundError,
    SessionService,
)
from bbz_core.auth.tokens import hash_refresh_token
from bbz_core.authorization import PermissionService
from bbz_core.infra.models.identity import AuthIdentity, User
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore
from bbz_core.infra.repositories.local_credentials import SqlAlchemyCredentialStore
from bbz_core.infra.repositories.mfa_policy import MfaPolicyService
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore
from bbz_core.infra.repositories.totp import TotpRepository
from bbz_core.settings import get_settings

if TYPE_CHECKING:
    from bbz_core.infra.repositories.webauthn import WebauthnService

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    totp: str | None = None  # TOTP or recovery code, when the account has MFA
    #: a WebAuthn assertion (navigator.credentials.get result, JSON) — E21-06
    webauthn: str | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    display_name: str
    status: str


class LoginResponse(BaseModel):
    user: UserOut
    must_change_password: bool
    csrf_token: str
    #: this account's role requires MFA (E21-05) but has none yet — still inside
    #: the grace period. The client should prompt enrolment before ``mfa_grace_until``.
    mfa_enrolment_required: bool = False
    mfa_grace_until: _dt.datetime | None = None


class MeResponse(BaseModel):
    user: UserOut
    permissions: list[str]
    scopes: list[str]


def _set_cookie(resp: Response, name: str, value: str, *, max_age: int, http_only: bool) -> None:
    s = get_settings()
    resp.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=http_only,
        secure=s.session_cookie_secure,
        samesite="lax",
        domain=s.session_cookie_domain,
        path="/",
    )


def _clear_cookie(resp: Response, name: str) -> None:
    s = get_settings()
    resp.delete_cookie(name, domain=s.session_cookie_domain, path="/")


async def _load_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


def _webauthn_service(session: AsyncSession) -> WebauthnService:
    from bbz_core.infra.repositories.webauthn import WebauthnService

    return WebauthnService(session)


async def _mfa_satisfied(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Does this user have an active second factor — a local TOTP **or** a
    WebAuthn credential (E21-06)? Checked regardless of which provider is logging
    them in now: a directory/OIDC user who also enrolled a local factor satisfies
    their role's MFA requirement with it."""
    aid = (
        await session.execute(
            select(AuthIdentity.id).where(
                AuthIdentity.user_id == user_id, AuthIdentity.provider == "local"
            )
        )
    ).scalar_one_or_none()
    if aid is None:
        return False
    if await TotpService(TotpRepository(session)).is_active(aid):
        return True
    return await _webauthn_service(session).has_active(user_id)


@dataclass(frozen=True)
class _MfaGate:
    blocked: bool
    grace_until: _dt.datetime | None


async def _enforce_mfa_policy(
    session: AsyncSession, user_id: uuid.UUID, *, satisfied: bool, external: bool
) -> _MfaGate:
    """Role-based MFA requirement (E21-05). ``external`` logins (OIDC/LDAP) can
    be exempted via ``mfa_policy_enforce_external=False`` — they have no local
    TOTP to challenge unless the same user also enrolled one locally."""
    if external and not get_settings().mfa_policy_enforce_external:
        return _MfaGate(blocked=False, grace_until=None)
    req = await MfaPolicyService(session).evaluate(user_id)
    if req.blocks(satisfied=satisfied):
        return _MfaGate(blocked=True, grace_until=None)
    grace = req.grace_until if (req.required and req.in_grace and not satisfied) else None
    return _MfaGate(blocked=False, grace_until=grace)


@contextlib.contextmanager
def _translate_oidc() -> Iterator[None]:
    from bbz_core.auth.oidc import OidcError, OidcIdTokenInvalid, OidcStateError
    from bbz_core.infra.repositories.oidc_login import (
        OidcProviderNotConfigured,
        OidcUserNotProvisioned,
    )

    try:
        yield
    except OidcProviderNotConfigured as exc:
        raise NotFoundError("no such OIDC provider") from exc
    except (OidcStateError, OidcIdTokenInvalid, OidcUserNotProvisioned) as exc:
        # a forged/stale callback, a bad token, or an unprovisioned principal —
        # one generic 401, no detail leak
        raise UnauthorizedError("authentication failed") from exc
    except OidcError as exc:
        # the IdP itself is unreachable / returned garbage
        raise ServiceUnavailableError("the identity provider is unavailable") from exc


async def _try_ldap_login(
    session: AsyncSession,
    body: LoginRequest,
    *,
    client_id: str | None,
    workplace_id: str | None,
) -> User | None:
    """Attempt a directory bind. Returns the BBZ user on success, ``None`` on any
    LDAP failure (the caller then reports the generic ``invalid credentials``)."""
    from bbz_core.auth.ldap import LdapError
    from bbz_core.infra.repositories.ldap_login import LdapLoginService

    try:
        user_id = await LdapLoginService(session).authenticate(
            body.username, body.password, client_id=client_id, workplace_id=workplace_id
        )
    except LdapError:
        return None
    return await _load_user(session, user_id)


async def _issue_session(
    *,
    session: AsyncSession,
    request: Request,
    response: Response,
    user_id: uuid.UUID,
    client_id: str | None,
    workplace_id: str | None,
    mfa_verified: bool = False,
) -> str:
    """Start a session for ``user_id``, set the access / refresh / CSRF cookies,
    and write the ``SESSION_STARTED`` audit row. Returns the CSRF token. The
    caller is responsible for the ``LOGIN_SUCCEEDED`` audit (the reason differs
    per flow). Takes a bare id (not an ORM object) because an earlier commit —
    e.g. a WebAuthn challenge write — may have expired it. ``mfa_verified``
    stamps the session so a step-up right after login doesn't ask again (E21-05)."""
    tokens = await SessionService(SqlAlchemySessionStore(session)).start(
        user_id,
        client_id=client_id,
        workplace_id=workplace_id,
        user_agent=request.headers.get("user-agent"),
        mfa_verified=mfa_verified,
    )
    await AuditWriter(session).record(
        AuditAction.SESSION_STARTED,
        actor_user_id=user_id,
        actor_client_id=client_id,
        workplace_id=workplace_id,
        target_type="session",
        target_id=str(tokens.session_id),
    )
    csrf = secrets.token_urlsafe(32)
    _set_cookie(
        response,
        ACCESS_COOKIE,
        tokens.access_token,
        max_age=tokens.access_ttl_seconds,
        http_only=True,
    )
    _set_cookie(
        response,
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=tokens.refresh_ttl_seconds,
        http_only=True,
    )
    _set_cookie(response, CSRF_COOKIE, csrf, max_age=tokens.refresh_ttl_seconds, http_only=False)
    return csrf


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
) -> LoginResponse:
    client_id = request.headers.get("x-client-id")
    workplace_id = request.headers.get("x-workplace-id")
    audit = AuditWriter(session)

    registry = AuthProviderRegistry.build(SqlAlchemyCredentialStore(session))
    outcome = await registry.default().authenticate_password(body.username, body.password)

    if outcome.result is LocalAuthResult.BAD_CREDENTIALS and "ldap_ad" in registry.names():
        # not a (valid) local account — fall back to the directory (E21-03)
        ldap_user = await _try_ldap_login(
            session, body, client_id=client_id, workplace_id=workplace_id
        )
        if ldap_user is not None:
            lu_id, lu_name, lu_status = ldap_user.id, ldap_user.display_name, ldap_user.status
            satisfied = await _mfa_satisfied(session, lu_id)
            gate = await _enforce_mfa_policy(session, lu_id, satisfied=satisfied, external=True)
            if gate.blocked:
                await audit.record(
                    AuditAction.LOGIN_FAILED,
                    actor_user_id=lu_id,
                    actor_client_id=client_id,
                    workplace_id=workplace_id,
                    target_type="login_attempt",
                    target_id=body.username[:64],
                )
                raise MfaRequiredError("multi-factor authentication is required for this account")
            csrf = await _issue_session(
                session=session,
                request=request,
                response=response,
                user_id=lu_id,
                client_id=client_id,
                workplace_id=workplace_id,
                mfa_verified=satisfied,
            )
            return LoginResponse(
                user=UserOut(id=lu_id, display_name=lu_name, status=lu_status),
                must_change_password=False,
                csrf_token=csrf,
                mfa_enrolment_required=gate.grace_until is not None,
                mfa_grace_until=gate.grace_until,
            )

    if outcome.result is not LocalAuthResult.SUCCESS or outcome.user_id is None:
        await audit.record(
            AuditAction.ACCOUNT_LOCKED
            if outcome.result is LocalAuthResult.LOCKED
            else AuditAction.LOGIN_FAILED,
            actor_client_id=client_id,
            workplace_id=workplace_id,
            target_type="login_attempt",
            target_id=body.username[:64],
        )
        # One generic failure — no account-existence or lockout-reason leak.
        raise UnauthorizedError("invalid credentials")

    user = await _load_user(session, outcome.user_id)
    if user is None:
        raise UnauthorizedError("invalid credentials")
    user_id, user_name, user_status = user.id, user.display_name, user.status

    aid = (
        await session.execute(
            select(AuthIdentity.id).where(
                AuthIdentity.provider == "local", AuthIdentity.subject == body.username
            )
        )
    ).scalar_one_or_none()
    mfa = TotpService(TotpRepository(session))
    totp_active = aid is not None and await mfa.is_active(aid)
    webauthn_active = await _webauthn_service(session).has_active(user_id)
    mfa_verified = False

    gate = await _enforce_mfa_policy(
        session, user_id, satisfied=(totp_active or webauthn_active), external=False
    )
    if gate.blocked:
        await audit.record(
            AuditAction.LOGIN_FAILED,
            actor_user_id=user_id,
            actor_client_id=client_id,
            workplace_id=workplace_id,
            target_type="login_attempt",
            target_id=body.username[:64],
        )
        raise MfaRequiredError("multi-factor authentication is required for this account")

    if body.webauthn and webauthn_active:
        if not await _webauthn_service(session).verify_authentication(
            user_id, response=body.webauthn
        ):
            await audit.record(
                AuditAction.MFA_CHALLENGE_FAILED, actor_user_id=user_id, actor_client_id=client_id
            )
            raise UnauthorizedError("invalid credentials")
        mfa_verified = True
    elif totp_active and body.totp:
        assert aid is not None
        result = await mfa.challenge(aid, body.totp)
        if result is ChallengeResult.BAD:
            await audit.record(
                AuditAction.MFA_CHALLENGE_FAILED, actor_user_id=user_id, actor_client_id=client_id
            )
            raise UnauthorizedError("invalid credentials")
        if result is ChallengeResult.RECOVERY_USED:
            await audit.record(AuditAction.MFA_RECOVERY_USED, actor_user_id=user_id)
        mfa_verified = True
    elif webauthn_active or totp_active:
        # a factor exists but none was supplied — challenge (WebAuthn first)
        if webauthn_active:
            options = await _webauthn_service(session).begin_authentication(user_id)
            raise WebauthnRequiredError("second factor required", details={"options": options})
        raise TotpRequiredError("second factor required")

    await audit.record(
        AuditAction.LOGIN_SUCCEEDED,
        actor_user_id=user_id,
        actor_client_id=client_id,
        workplace_id=workplace_id,
    )
    csrf = await _issue_session(
        session=session,
        request=request,
        response=response,
        user_id=user_id,
        client_id=client_id,
        workplace_id=workplace_id,
        mfa_verified=mfa_verified,
    )
    return LoginResponse(
        user=UserOut(id=user_id, display_name=user_name, status=user_status),
        must_change_password=outcome.must_change_password,
        csrf_token=csrf,
        mfa_enrolment_required=gate.grace_until is not None,
        mfa_grace_until=gate.grace_until,
    )


class OidcStartResponse(BaseModel):
    authorization_url: str


class OidcCallbackRequest(BaseModel):
    code: str
    state: str


@router.get("/oidc/{provider}/start", response_model=OidcStartResponse)
async def oidc_start(
    provider: str,
    session: AsyncSession = Depends(db_session),
) -> OidcStartResponse:
    """Begin an external login: returns the IdP authorization URL the SPA
    redirects to. ``state`` / ``nonce`` / the PKCE verifier are held server-side."""
    from bbz_core.infra.repositories.oidc_login import OidcLoginService

    with _translate_oidc():
        url = await OidcLoginService(session).begin(provider)
    return OidcStartResponse(authorization_url=url)


@router.post("/oidc/{provider}/callback", response_model=LoginResponse)
async def oidc_callback(
    provider: str,
    body: OidcCallbackRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
) -> LoginResponse:
    """Finish an external login: exchange the code, validate the ID token, and
    mint a BBZ session (same cookies as ``/login``)."""
    from bbz_core.infra.repositories.oidc_login import OidcLoginService

    client_id = request.headers.get("x-client-id")
    workplace_id = request.headers.get("x-workplace-id")
    with _translate_oidc():
        user_id = await OidcLoginService(session).complete(
            provider,
            code=body.code,
            state=body.state,
            client_id=client_id,
            workplace_id=workplace_id,
        )
    user = await _load_user(session, user_id)
    if user is None:  # the identity resolved to a user that has since gone
        raise UnauthorizedError("authentication failed")
    u_name, u_status = user.display_name, user.status

    satisfied = await _mfa_satisfied(session, user_id)
    gate = await _enforce_mfa_policy(session, user_id, satisfied=satisfied, external=True)
    if gate.blocked:
        await AuditWriter(session).record(
            AuditAction.LOGIN_FAILED,
            actor_user_id=user_id,
            actor_client_id=client_id,
            workplace_id=workplace_id,
        )
        raise MfaRequiredError("multi-factor authentication is required for this account")

    csrf = await _issue_session(
        session=session,
        request=request,
        response=response,
        user_id=user_id,
        client_id=client_id,
        workplace_id=workplace_id,
        mfa_verified=satisfied,
    )
    return LoginResponse(
        user=UserOut(id=user_id, display_name=u_name, status=u_status),
        must_change_password=False,
        csrf_token=csrf,
        mfa_enrolment_required=gate.grace_until is not None,
        mfa_grace_until=gate.grace_until,
    )


@router.post(
    "/refresh",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def refresh(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise UnauthorizedError("no refresh token")
    try:
        access, _ = await SessionService(SqlAlchemySessionStore(session)).refresh(token)
    except (SessionNotFoundError, SessionExpiredError) as exc:
        _clear_cookie(response, ACCESS_COOKIE)
        _clear_cookie(response, REFRESH_COOKIE)
        raise UnauthorizedError("refresh token is invalid or expired") from exc
    _set_cookie(
        response,
        ACCESS_COOKIE,
        access,
        max_age=get_settings().access_token_ttl_seconds,
        http_only=True,
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(db_session),
) -> Response:
    token = request.cookies.get(REFRESH_COOKIE)
    if token:
        store = SqlAlchemySessionStore(session)
        record = await store.get_active_by_refresh(hash_refresh_token(token))
        await SessionService(store).revoke_by_refresh(token)
        if record is not None:
            await AuditWriter(session).record(
                AuditAction.SESSION_ENDED,
                actor_user_id=record.user_id,
                target_type="session",
                target_id=str(record.id),
                reason="logout",
            )
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        _clear_cookie(response, name)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
async def me(
    ctx: AuthContext = Depends(current_auth),
    session: AsyncSession = Depends(db_session),
) -> MeResponse:
    user = await _load_user(session, ctx.user_id)
    if user is None:
        raise UnauthorizedError("user no longer exists")
    effective = await PermissionService(SqlAlchemyGrantStore(session)).effective(ctx.user_id)
    keys = effective.keys()
    return MeResponse(
        user=UserOut(id=user.id, display_name=user.display_name, status=user.status),
        permissions=sorted(keys),
        scopes=sorted({s for k in keys for s in effective.scopes_for(k)}),
    )
