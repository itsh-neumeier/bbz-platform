"""SQLAlchemy implementation of :class:`bbz_core.authorization.GrantStore`."""

from __future__ import annotations

import uuid

from sqlalchemy import select, union
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization.model import Grant
from bbz_core.infra.models.rbac import (
    GroupRole,
    Permission,
    RolePermission,
    UserGroup,
    UserRole,
)


class SqlAlchemyGrantStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def grants_for_user(self, user_id: uuid.UUID) -> list[Grant]:
        direct = select(UserRole.role_id).where(UserRole.user_id == user_id)
        via_group = (
            select(GroupRole.role_id)
            .join(UserGroup, UserGroup.group_id == GroupRole.group_id)
            .where(UserGroup.user_id == user_id)
        )
        role_ids = union(direct, via_group).subquery()

        rows = await self._s.execute(
            select(Permission.key, RolePermission.scope)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(select(role_ids.c.role_id)))
        )
        return [Grant(permission_key=key, scope=scope) for key, scope in rows.all()]
