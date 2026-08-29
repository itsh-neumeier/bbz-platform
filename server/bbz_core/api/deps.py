"""Shared FastAPI dependencies: DB session, current auth context, CSRF guard."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.errors import ForbiddenError, UnauthorizedError
from bbz_core.auth.sessions import SessionService
from bbz_core.auth.tokens import TokenError, decode_access_token
from bbz_core.infra.db import session_scope
from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore

ACCESS_COOKIE = "bbz_access"
REFRESH_COOKIE = "bbz_refresh"
CSRF_COOKIE = "bbz_csrf"
CSRF_HEADER = "x-csrf-token"


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
    return AuthContext(user_id=claims.user_id, session_id=claims.session_id)


async def require_csrf(request: Request) -> None:
    """Double-submit CSRF check — only for cookie-authenticated write requests.

    Bearer-token clients (agents) are not cookie-based and are exempt.
    """
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or cookie != header:
        raise ForbiddenError("missing or invalid CSRF token")
