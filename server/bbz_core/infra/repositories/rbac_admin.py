"""Write-side repository for RBAC administration (E02-09).

Role/permission changes take effect immediately: the permission service reads
the DB per request, so no cache invalidation or restart is needed.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.rbac import (
    Group,
    GroupRole,
    Permission,
    Role,
    RolePermission,
    UserGroup,
    UserRole,
)


class RbacAdminError(Exception):
    pass


def _validate_condition(condition: dict[str, Any]) -> None:
    """Reject a stored-but-broken RBAC condition at write time (ADR-0027)."""
    from bbz_rule_dsl import RBAC_CONTEXT, RuleDslError

    try:
        RBAC_CONTEXT.validate(condition)
    except RuleDslError as exc:
        raise RbacAdminError(f"invalid condition: {exc}") from exc


class LastAdminError(RbacAdminError):
    """The change would leave nobody able to manage permissions."""


@dataclass(frozen=True)
class PermissionAssignment:
    permission_key: str
    scope: str = "global"
    condition: dict[str, Any] | None = None


class RbacAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- roles -----------------------------------------------------------

    async def list_roles(self) -> Sequence[Role]:
        return (await self._s.execute(select(Role).order_by(Role.key))).scalars().all()

    async def get_role(self, role_id: uuid.UUID) -> Role | None:
        return await self._s.get(Role, role_id)

    async def get_role_by_key(self, key: str) -> Role | None:
        return (await self._s.execute(select(Role).where(Role.key == key))).scalar_one_or_none()

    async def create_role(self, key: str, name: str) -> Role:
        existing = await self.get_role_by_key(key)
        if existing is not None:  # natural-key idempotency
            return existing
        role = Role(key=key, name=name, builtin=False)
        self._s.add(role)
        await self._s.flush()
        await self._s.commit()
        return role

    async def rename_role(self, role: Role, name: str) -> Role:
        role.name = name
        await self._s.commit()
        return role

    async def delete_role(self, role: Role) -> None:
        if role.builtin:
            raise RbacAdminError("builtin roles cannot be deleted")
        had_admin = await self._any_admin()
        await self._s.delete(role)
        await self._s.flush()
        await self._guard_last_admin(had_admin)
        await self._s.commit()

    # --- role permissions (declarative replace) ------------------------

    async def get_role_permissions(self, role_id: uuid.UUID) -> list[PermissionAssignment]:
        rows = await self._s.execute(
            select(Permission.key, RolePermission.scope, RolePermission.condition)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return [PermissionAssignment(k, s, c) for k, s, c in rows.all()]

    async def set_role_permissions(
        self, role: Role, assignments: Sequence[PermissionAssignment]
    ) -> None:
        keys = {a.permission_key for a in assignments}
        rows = (
            await self._s.execute(
                select(Permission.key, Permission.id).where(Permission.key.in_(keys))
            )
        ).all()
        perm_ids: dict[str, uuid.UUID] = dict(rows)  # type: ignore[arg-type]
        missing = keys - set(perm_ids)
        if missing:
            raise RbacAdminError(f"unknown permission keys: {sorted(missing)}")

        for a in assignments:
            if a.condition is not None:
                _validate_condition(a.condition)

        had_admin = await self._any_admin()
        await self._s.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for a in assignments:
            self._s.add(
                RolePermission(
                    role_id=role.id,
                    permission_id=perm_ids[a.permission_key],
                    scope=a.scope,
                    condition=a.condition,
                )
            )
        await self._s.flush()
        await self._guard_last_admin(had_admin)
        await self._s.commit()

    # --- assignments --------------------------------------------------

    async def assign_user_role(
        self,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        granted_by: uuid.UUID | None,
        *,
        valid_from: _dt.datetime | None = None,
        valid_to: _dt.datetime | None = None,
    ) -> None:
        if valid_from and valid_to and valid_to <= valid_from:
            raise RbacAdminError("valid_to must be after valid_from")
        existing = await self._s.get(UserRole, (user_id, role_id))
        if existing is None:
            self._s.add(
                UserRole(
                    user_id=user_id,
                    role_id=role_id,
                    granted_by=granted_by,
                    valid_from=valid_from,
                    valid_to=valid_to,
                )
            )
        else:  # re-assigning updates the validity window
            existing.valid_from = valid_from
            existing.valid_to = valid_to
        await self._s.commit()

    async def revoke_user_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> None:
        had_admin = await self._any_admin()
        await self._s.execute(
            delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        )
        await self._s.flush()
        await self._guard_last_admin(had_admin)
        await self._s.commit()

    async def list_groups(self) -> Sequence[Group]:
        return (await self._s.execute(select(Group).order_by(Group.key))).scalars().all()

    async def create_group(self, key: str, name: str) -> Group:
        existing = (
            await self._s.execute(select(Group).where(Group.key == key))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        group = Group(key=key, name=name)
        self._s.add(group)
        await self._s.flush()
        await self._s.commit()
        return group

    async def assign_group_role(self, group_id: uuid.UUID, role_id: uuid.UUID) -> None:
        if await self._s.get(GroupRole, (group_id, role_id)) is None:
            self._s.add(GroupRole(group_id=group_id, role_id=role_id))
            await self._s.commit()

    async def revoke_group_role(self, group_id: uuid.UUID, role_id: uuid.UUID) -> None:
        had_admin = await self._any_admin()
        await self._s.execute(
            delete(GroupRole).where(GroupRole.group_id == group_id, GroupRole.role_id == role_id)
        )
        await self._s.flush()
        await self._guard_last_admin(had_admin)
        await self._s.commit()

    # --- last-admin protection ---------------------------------------

    async def _any_admin(self) -> bool:
        """Does at least one user hold ``permissions.manage`` (direct or via group)?"""
        manage_roles = (
            select(RolePermission.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Permission.key == "permissions.manage")
        )
        direct = select(UserRole.user_id).where(UserRole.role_id.in_(manage_roles))
        via_group = (
            select(UserGroup.user_id)
            .join(GroupRole, GroupRole.group_id == UserGroup.group_id)
            .where(GroupRole.role_id.in_(manage_roles))
        )
        return bool(
            await self._s.scalar(select(exists(direct.union(via_group).subquery().select())))
        )

    async def _guard_last_admin(self, had_admin: bool) -> None:
        """Raise if the just-applied (un-committed) change removed the last admin."""
        if had_admin and not await self._any_admin():
            await self._s.rollback()
            raise LastAdminError("this change would leave nobody able to manage permissions")
