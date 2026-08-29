"""Interactive authentication endpoints: login / refresh / logout / me.

Cookie-based for the web/kiosk clients (HttpOnly access + refresh, plus a
readable double-submit CSRF token). Bearer tokens also work for agents.
Effective permissions on ``/me`` come from the permission service (E02-08).
"""

from __future__ import annotations

import secrets
import uuid

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
from bbz_core.api.errors import UnauthorizedError
from bbz_core.audit import AuditAction, AuditWriter
from bbz_core.auth.local import LocalAuthResult
from bbz_core.auth.registry import AuthProviderRegistry
from bbz_core.auth.sessions import (
    SessionExpiredError,
    SessionNotFoundError,
    SessionService,
)
from bbz_core.auth.tokens import hash_refresh_token
from bbz_core.authorization import PermissionService
from bbz_core.infra.models.identity import User
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore
from bbz_core.infra.repositories.local_credentials import SqlAlchemyCredentialStore
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore
from bbz_core.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    display_name: str
    status: str


class LoginResponse(BaseModel):
    user: UserOut
    must_change_password: bool
    csrf_token: str


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

    tokens = await SessionService(SqlAlchemySessionStore(session)).start(
        outcome.user_id,
        client_id=client_id,
        workplace_id=workplace_id,
        user_agent=request.headers.get("user-agent"),
    )
    await audit.record(
        AuditAction.LOGIN_SUCCEEDED,
        actor_user_id=user.id,
        actor_client_id=client_id,
        workplace_id=workplace_id,
    )
    await audit.record(
        AuditAction.SESSION_STARTED,
        actor_user_id=user.id,
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
    return LoginResponse(
        user=UserOut(id=user.id, display_name=user.display_name, status=user.status),
        must_change_password=outcome.must_change_password,
        csrf_token=csrf,
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
