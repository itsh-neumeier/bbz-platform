"""Shared FastAPI dependencies: DB session and the current auth context.

CSRF is enforced centrally by :class:`bbz_core.api.csrf.CsrfMiddleware`, not as a
per-route dependency.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.errors import UnauthorizedError
from bbz_core.auth.sessions import SessionService
from bbz_core.auth.tokens import TokenError, decode_access_token
from bbz_core.infra.db import session_scope
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore
from bbz_core.logging import user_id as _user_id_ctx

ACCESS_COOKIE = "bbz_access"
REFRESH_COOKIE = "bbz_refresh"


async def db_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    session_id: uuid.UUID


def _bearer_or_cookie(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(ACCESS_COOKIE)


async def current_auth(
    request: Request, session: AsyncSession = Depends(db_session)
) -> AuthContext:
    token = _bearer_or_cookie(request)
    if not token:
        raise UnauthorizedError("authentication required")
    try:
        claims = decode_access_token(token)
    except TokenError as exc:
        raise UnauthorizedError("invalid or expired token") from exc
    sessions = SessionService(SqlAlchemySessionStore(session))
    if not await sessions.is_active(claims.session_id):
        raise UnauthorizedError("session is no longer active")
    _user_id_ctx.set(str(claims.user_id))  # -> the `user_id` log field (E22-03)
    return AuthContext(user_id=claims.user_id, session_id=claims.session_id)
