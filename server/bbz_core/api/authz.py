"""``require(permission)`` — declarative authorization for API endpoints.

    @router.post("/events/{id}/takeover")
    async def takeover(id: UUID, ctx: AuthContext = Depends(require("events.takeover"))):
        ...

401 (no/invalid auth) and 403 (authenticated but not allowed) are kept distinct;
both render the uniform error envelope with ``correlation_id`` (ADR-0012).

A ``scope`` extractor turns the request into a :class:`ScopeContext` so the
check is scope-aware (E02-07); without one it is scope-agnostic.

Every ``require(...)`` dependency carries ``_bbz_permission`` so a contract test
can prove no ``/api/v1`` write route forgot to declare one.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.deps import AuthContext, current_auth, db_session
from bbz_core.api.errors import ForbiddenError, StepUpRequiredError
from bbz_core.audit import AuditAction, AuditService
from bbz_core.authorization import PermissionService, ScopeContext
from bbz_core.authorization.keys import assert_known
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore
from bbz_core.settings import get_settings

ScopeExtractor = Callable[[Request, AuthContext], Awaitable[ScopeContext]]


def require(
    permission: str, *, scope: ScopeExtractor | None = None
) -> Callable[..., Awaitable[AuthContext]]:
    assert_known(permission)  # fail at import time, not per request

    async def _dependency(
        request: Request,
        ctx: AuthContext = Depends(current_auth),
        session: AsyncSession = Depends(db_session),
    ) -> AuthContext:
        svc = PermissionService(SqlAlchemyGrantStore(session))
        if scope is None:
            allowed = await svc.authorize(ctx.user_id, permission)
        else:
            allowed = await svc.authorize_scoped(ctx.user_id, permission, await scope(request, ctx))
        if not allowed:
            raise ForbiddenError(f"missing permission: {permission}")
        return ctx

    _dependency._bbz_permission = permission  # type: ignore[attr-defined]
    return _dependency


def require_stepup(
    permission: str, *, scope: ScopeExtractor | None = None
) -> Callable[..., Awaitable[AuthContext]]:
    """Like :func:`require`, but for a small set of sensitive permissions
    (``mfa_stepup_permissions``, E21-05) it also demands a **fresh** MFA
    verification on this session — one within ``mfa_stepup_max_age_seconds``
    (a login that itself included a TOTP/recovery challenge counts, so does a
    recent ``POST /auth/step-up``). Audits ``MFA_STEPUP_REQUIRED`` when it blocks.
    """
    base = require(permission, scope=scope)

    async def _dependency(
        ctx: AuthContext = Depends(base),
        session: AsyncSession = Depends(db_session),
    ) -> AuthContext:
        settings = get_settings()
        if permission not in settings.mfa_stepup_permissions:
            return ctx
        record = await SqlAlchemySessionStore(session).get_active(ctx.session_id)
        age = (
            (_dt.datetime.now(_dt.UTC) - record.mfa_verified_at).total_seconds()
            if record is not None and record.mfa_verified_at is not None
            else None
        )
        if age is not None and age <= settings.mfa_stepup_max_age_seconds:
            return ctx
        await session.rollback()  # close the read tx `get_active` autobegan
        async with session.begin():
            await AuditService(session).write(
                AuditAction.MFA_STEPUP_REQUIRED,
                actor_user_id=ctx.user_id,
                target_type="permission",
                target_id=permission,
            )
        raise StepUpRequiredError(f"step-up verification required for: {permission}")

    _dependency._bbz_permission = permission  # type: ignore[attr-defined]
    return _dependency
