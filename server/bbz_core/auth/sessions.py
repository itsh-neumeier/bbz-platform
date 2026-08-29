"""Session lifecycle: start, refresh, revoke.

Storage-agnostic (a :class:`SessionStore`). Revocation lives in the store so
both application nodes stop honouring a session immediately after logout or
user deactivation (E02-05 / E02-10).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from bbz_core.auth.tokens import (
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
)
from bbz_core.settings import get_settings


class SessionExpiredError(Exception):
    pass


class SessionNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class SessionRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    expires_at: _dt.datetime
    revoked_at: _dt.datetime | None


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    session_id: uuid.UUID
    access_ttl_seconds: int
    refresh_ttl_seconds: int


class SessionStore(Protocol):
    async def create(
        self,
        *,
        user_id: uuid.UUID,
        refresh_hash: str,
        expires_at: _dt.datetime,
        client_id: str | None,
        workplace_id: str | None,
        user_agent: str | None,
    ) -> uuid.UUID: ...
    async def get_active_by_refresh(self, refresh_hash: str) -> SessionRecord | None: ...
    async def get_active(self, session_id: uuid.UUID) -> SessionRecord | None: ...
    async def touch(self, session_id: uuid.UUID) -> None: ...
    async def revoke(self, session_id: uuid.UUID) -> None: ...
    async def revoke_by_refresh(self, refresh_hash: str) -> None: ...
    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int: ...


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class SessionService:
    def __init__(self, store: SessionStore, *, clock: Callable[[], _dt.datetime] = _utcnow) -> None:
        self._store = store
        self._now = clock

    async def start(
        self,
        user_id: uuid.UUID,
        *,
        client_id: str | None = None,
        workplace_id: str | None = None,
        user_agent: str | None = None,
    ) -> IssuedTokens:
        s = get_settings()
        refresh = new_refresh_token()
        expires_at = self._now() + _dt.timedelta(seconds=s.refresh_token_ttl_seconds)
        session_id = await self._store.create(
            user_id=user_id,
            refresh_hash=hash_refresh_token(refresh),
            expires_at=expires_at,
            client_id=client_id,
            workplace_id=workplace_id,
            user_agent=user_agent,
        )
        return IssuedTokens(
            access_token=issue_access_token(user_id, session_id),
            refresh_token=refresh,
            session_id=session_id,
            access_ttl_seconds=s.access_token_ttl_seconds,
            refresh_ttl_seconds=s.refresh_token_ttl_seconds,
        )

    async def refresh(self, refresh_token: str) -> tuple[str, uuid.UUID]:
        record = await self._store.get_active_by_refresh(hash_refresh_token(refresh_token))
        if record is None:
            raise SessionNotFoundError
        if record.revoked_at is not None:
            raise SessionNotFoundError
        if record.expires_at <= self._now():
            raise SessionExpiredError
        await self._store.touch(record.id)
        return issue_access_token(record.user_id, record.id), record.id

    async def is_active(self, session_id: uuid.UUID) -> bool:
        record = await self._store.get_active(session_id)
        return record is not None and record.expires_at > self._now()

    async def revoke(self, session_id: uuid.UUID) -> None:
        await self._store.revoke(session_id)

    async def revoke_by_refresh(self, refresh_token: str) -> None:
        await self._store.revoke_by_refresh(hash_refresh_token(refresh_token))

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        return await self._store.revoke_all_for_user(user_id)
