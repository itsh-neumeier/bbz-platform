"""SQLAlchemy implementation of :class:`bbz_core.authorization.GrantStore`."""

from __future__ import annotations

import datetime as _dt
import uuid

from sqlalchemy import or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization.model import Grant
from bbz_core.infra.models.rbac import (
    GroupRole,
    Permission,
    PermissionDelegation,
    RolePermission,
    UserGroup,
    UserRole,
)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class SqlAlchemyGrantStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def grants_for_user(self, user_id: uuid.UUID) -> list[Grant]:
        now = _now()
        # direct role grants — only those inside their validity window (E21-07)
        direct = select(UserRole.role_id).where(
            UserRole.user_id == user_id,
            or_(UserRole.valid_from.is_(None), UserRole.valid_from <= now),
            or_(UserRole.valid_to.is_(None), UserRole.valid_to >= now),
        )
        via_group = (
            select(GroupRole.role_id)
            .join(UserGroup, UserGroup.group_id == GroupRole.group_id)
            .where(UserGroup.user_id == user_id)
        )
        role_ids = union(direct, via_group).subquery()

        rows = await self._s.execute(
            select(Permission.key, RolePermission.scope, RolePermission.condition)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(select(role_ids.c.role_id)))
        )
        grants = [
            Grant(permission_key=key, scope=scope, condition=condition)
            for key, scope, condition in rows.all()
        ]

        # active delegations lent to this user (E21-07) — unconditional
        delegated = await self._s.execute(
            select(PermissionDelegation.permission_key, PermissionDelegation.scope).where(
                PermissionDelegation.to_user_id == user_id,
                PermissionDelegation.revoked_at.is_(None),
                PermissionDelegation.expires_at > now,
            )
        )
        grants.extend(Grant(permission_key=key, scope=scope) for key, scope in delegated.all())
        return grants
