"""SQLAlchemy implementation of :class:`bbz_core.auth.sessions.SessionStore`."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.auth.sessions import SessionRecord
from bbz_core.infra.models.session import Session


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class SqlAlchemySessionStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        user_id: uuid.UUID,
        refresh_hash: str,
        expires_at: _dt.datetime,
        client_id: str | None,
        workplace_id: str | None,
        user_agent: str | None,
    ) -> uuid.UUID:
        row = Session(
            user_id=user_id,
            refresh_token_hash=refresh_hash,
            expires_at=expires_at,
            client_id=client_id,
            workplace_id=workplace_id,
            user_agent=user_agent,
        )
        self._s.add(row)
        await self._s.flush()
        await self._s.commit()
        return row.id

    def _record(self, row: Session | None) -> SessionRecord | None:
        if row is None:
            return None
        return SessionRecord(
            id=row.id,
            user_id=row.user_id,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
        )

    async def get_active_by_refresh(self, refresh_hash: str) -> SessionRecord | None:
        row = (
            await self._s.execute(
                select(Session).where(
                    Session.refresh_token_hash == refresh_hash,
                    Session.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        return self._record(row)

    async def get_active(self, session_id: uuid.UUID) -> SessionRecord | None:
        row = (
            await self._s.execute(
                select(Session).where(Session.id == session_id, Session.revoked_at.is_(None))
            )
        ).scalar_one_or_none()
        return self._record(row)

    async def touch(self, session_id: uuid.UUID) -> None:
        await self._s.execute(
            update(Session).where(Session.id == session_id).values(last_used_at=_utcnow())
        )
        await self._s.commit()

    async def revoke(self, session_id: uuid.UUID) -> None:
        await self._s.execute(
            update(Session)
            .where(Session.id == session_id, Session.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        await self._s.commit()

    async def revoke_by_refresh(self, refresh_hash: str) -> None:
        await self._s.execute(
            update(Session)
            .where(Session.refresh_token_hash == refresh_hash, Session.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        await self._s.commit()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        result = await self._s.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=_utcnow())
        )
        await self._s.commit()
        return int(result.rowcount)  # type: ignore[attr-defined]
