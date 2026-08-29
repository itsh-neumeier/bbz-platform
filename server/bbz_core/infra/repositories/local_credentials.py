"""SQLAlchemy implementation of :class:`bbz_core.auth.CredentialStore`."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.auth.local import CredentialRecord
from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User


class SqlAlchemyCredentialStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_by_username(self, username: str) -> CredentialRecord | None:
        row = (
            await self._s.execute(
                select(
                    User.id,
                    AuthIdentity.id,
                    LocalCredential.password_hash,
                    LocalCredential.must_change,
                    LocalCredential.failed_attempts,
                    LocalCredential.locked_until,
                    User.status,
                )
                .join(AuthIdentity, AuthIdentity.user_id == User.id)
                .join(
                    LocalCredential,
                    LocalCredential.auth_identity_id == AuthIdentity.id,
                )
                .where(AuthIdentity.provider == "local", AuthIdentity.subject == username)
            )
        ).first()
        if row is None:
            return None
        return CredentialRecord(
            user_id=row[0],
            auth_identity_id=row[1],
            password_hash=row[2],
            must_change=row[3],
            failed_attempts=row[4],
            locked_until=row[5],
            user_active=row[6] == "active",
        )

    async def record_failure(
        self, auth_identity_id: uuid.UUID, *, locked_until: _dt.datetime | None
    ) -> None:
        await self._s.execute(
            update(LocalCredential)
            .where(LocalCredential.auth_identity_id == auth_identity_id)
            .values(
                failed_attempts=LocalCredential.failed_attempts + 1,
                locked_until=locked_until,
            )
        )
        await self._s.commit()

    async def reset_failures(self, auth_identity_id: uuid.UUID) -> None:
        await self._s.execute(
            update(LocalCredential)
            .where(LocalCredential.auth_identity_id == auth_identity_id)
            .values(failed_attempts=0, locked_until=None)
        )
        await self._s.commit()

    async def update_hash(self, auth_identity_id: uuid.UUID, new_hash: str) -> None:
        await self._s.execute(
            update(LocalCredential)
            .where(LocalCredential.auth_identity_id == auth_identity_id)
            .values(password_hash=new_hash)
        )
        await self._s.commit()

    async def set_password(
        self, auth_identity_id: uuid.UUID, new_hash: str, *, must_change: bool
    ) -> None:
        stmt = insert(LocalCredential).values(
            auth_identity_id=auth_identity_id,
            password_hash=new_hash,
            must_change=must_change,
            failed_attempts=0,
            locked_until=None,
            password_changed_at=_dt.datetime.now(_dt.UTC),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[LocalCredential.auth_identity_id],
            set_={
                "password_hash": new_hash,
                "must_change": must_change,
                "failed_attempts": 0,
                "locked_until": None,
                "password_changed_at": _dt.datetime.now(_dt.UTC),
            },
        )
        await self._s.execute(stmt)
        await self._s.commit()
