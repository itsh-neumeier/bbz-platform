"""Temporary permission delegation (roadmap E21-07).

One user lends a single permission to another for a bounded time. The delegatee
gains it (via the grant store) until it expires or the delegator / an admin
revokes it — a revoke is effective on the delegatee's next request (the
permission service reads the DB per request). Audited both ways.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.authorization import PermissionService
from bbz_core.authorization.keys import assert_known
from bbz_core.authorization.scopes import Scope
from bbz_core.infra.models.rbac import PermissionDelegation
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class DelegationError(Exception):
    pass


class NotDelegatorsToGive(DelegationError):
    """The delegator does not currently hold the permission they tried to lend."""


class DelegationNotFound(LookupError):
    pass


@dataclass(frozen=True)
class DelegationView:
    id: uuid.UUID
    from_user_id: uuid.UUID
    to_user_id: uuid.UUID
    permission_key: str
    scope: str
    granted_at: _dt.datetime
    expires_at: _dt.datetime
    revoked_at: _dt.datetime | None

    @property
    def active(self) -> bool:
        return self.revoked_at is None and self.expires_at > _now()


def _view(d: PermissionDelegation) -> DelegationView:
    return DelegationView(
        id=d.id,
        from_user_id=d.from_user_id,
        to_user_id=d.to_user_id,
        permission_key=d.permission_key,
        scope=d.scope,
        granted_at=d.granted_at,
        expires_at=d.expires_at,
        revoked_at=d.revoked_at,
    )


class DelegationService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def delegate(
        self,
        *,
        from_user_id: uuid.UUID,
        to_user_id: uuid.UUID,
        permission_key: str,
        expires_at: _dt.datetime,
        scope: str = Scope.GLOBAL.value,
        actor_id: uuid.UUID | None = None,
    ) -> DelegationView:
        assert_known(permission_key)
        if scope not in {s.value for s in Scope}:
            raise DelegationError(f"unknown scope: {scope}")
        if expires_at <= _now():
            raise DelegationError("expires_at must be in the future")
        if from_user_id == to_user_id:
            raise DelegationError("cannot delegate to yourself")
        if not await PermissionService(SqlAlchemyGrantStore(self._s)).authorize(
            from_user_id, permission_key
        ):
            raise NotDelegatorsToGive(permission_key)

        await self._s.rollback()
        async with self._s.begin():
            row = PermissionDelegation(
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                permission_key=permission_key,
                scope=scope,
                expires_at=expires_at,
            )
            self._s.add(row)
            await self._s.flush()
            view = _view(row)  # capture before the commit expires the row
            await AuditService(self._s).write(
                AuditAction.PERMISSION_DELEGATED,
                actor_user_id=actor_id,
                target_type="user",
                target_id=str(to_user_id),
                after={
                    "permission": permission_key,
                    "scope": scope,
                    "from": str(from_user_id),
                    "expires_at": expires_at.isoformat(),
                },
            )
        return view

    async def revoke(self, delegation_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> None:
        await self._s.rollback()
        async with self._s.begin():
            row = await self._s.get(PermissionDelegation, delegation_id)
            if row is None:
                raise DelegationNotFound(str(delegation_id))
            if row.revoked_at is None:
                row.revoked_at = _now()
                await AuditService(self._s).write(
                    AuditAction.PERMISSION_DELEGATION_REVOKED,
                    actor_user_id=actor_id,
                    target_type="user",
                    target_id=str(row.to_user_id),
                    before={"permission": row.permission_key, "from": str(row.from_user_id)},
                )

    async def get(self, delegation_id: uuid.UUID) -> DelegationView | None:
        await self._s.rollback()
        row = await self._s.get(PermissionDelegation, delegation_id)
        return None if row is None else _view(row)

    async def list_involving(
        self, user_id: uuid.UUID, *, active_only: bool = False
    ) -> list[DelegationView]:
        await self._s.rollback()
        stmt = (
            select(PermissionDelegation)
            .where(
                or_(
                    PermissionDelegation.from_user_id == user_id,
                    PermissionDelegation.to_user_id == user_id,
                )
            )
            .order_by(PermissionDelegation.granted_at.desc())
        )
        if active_only:
            stmt = stmt.where(
                PermissionDelegation.revoked_at.is_(None),
                PermissionDelegation.expires_at > _now(),
            )
        return [_view(d) for d in (await self._s.execute(stmt)).scalars()]
