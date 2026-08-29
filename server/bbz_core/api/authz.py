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

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.deps import AuthContext, current_auth, db_session
from bbz_core.api.errors import ForbiddenError
from bbz_core.authorization import PermissionService, ScopeContext
from bbz_core.authorization.keys import assert_known
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore

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
