"""IdP group → BBZ role mapping + login-time role reconciliation (roadmap E21-02).

Admins configure "provider group X grants role Y"; on every external login the
user's mapped roles are recomputed from the current ``groups`` claim and
reconciled — new ones added, ones whose group is gone removed. Roles an admin
assigned by hand (no ``external_role_assignments`` row) are never touched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.models.auth_mapping import AuthGroupMapping, ExternalRoleAssignment
from bbz_core.infra.models.rbac import Role, UserRole


class UnknownRoleKey(ValueError):
    """A mapping referenced a ``roles.key`` that does not exist."""


class MappingNotFound(LookupError):
    pass


@dataclass(frozen=True)
class MappingView:
    id: uuid.UUID
    provider: str
    external_group: str
    role_key: str


def _view(m: AuthGroupMapping) -> MappingView:
    return MappingView(
        id=m.id, provider=m.provider, external_group=m.external_group, role_key=m.role_key
    )


class GroupMappingService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- CRUD (roles.manage) -------------------------------------

    async def list_mappings(self, *, provider: str | None = None) -> list[MappingView]:
        await self._s.rollback()
        stmt = select(AuthGroupMapping).order_by(
            AuthGroupMapping.provider, AuthGroupMapping.external_group, AuthGroupMapping.role_key
        )
        if provider:
            stmt = stmt.where(AuthGroupMapping.provider == provider)
        return [_view(m) for m in (await self._s.execute(stmt)).scalars()]

    async def create(
        self, *, provider: str, external_group: str, role_key: str, actor_id: uuid.UUID | None
    ) -> MappingView:
        await self._s.rollback()
        async with self._s.begin():
            role = (
                await self._s.execute(select(Role.id).where(Role.key == role_key))
            ).scalar_one_or_none()
            if role is None:
                raise UnknownRoleKey(role_key)
            mapping = AuthGroupMapping(
                provider=provider,
                external_group=external_group.strip(),
                role_key=role_key,
                created_by=actor_id,
            )
            self._s.add(mapping)
            await self._s.flush()
            await AuditService(self._s).write(
                AuditAction.AUTH_MAPPING_CHANGED,
                actor_user_id=actor_id,
                target_type="auth_group_mapping",
                target_id=str(mapping.id),
                after={
                    "provider": provider,
                    "group": external_group,
                    "role": role_key,
                    "op": "create",
                },
            )
        return _view(mapping)

    async def delete_mapping(self, mapping_id: uuid.UUID, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        async with self._s.begin():
            mapping = await self._s.get(AuthGroupMapping, mapping_id)
            if mapping is None:
                raise MappingNotFound(str(mapping_id))
            before = {
                "provider": mapping.provider,
                "group": mapping.external_group,
                "role": mapping.role_key,
            }
            await self._s.delete(mapping)
            await AuditService(self._s).write(
                AuditAction.AUTH_MAPPING_CHANGED,
                actor_user_id=actor_id,
                target_type="auth_group_mapping",
                target_id=str(mapping_id),
                before=before,
                after={"op": "delete"},
            )

    # --- login-time reconcile ----------------------------------

    async def sync_user_roles(
        self, *, user_id: uuid.UUID, provider: str, external_groups: tuple[str, ...]
    ) -> None:
        """Recompute this user's mapping-granted roles from ``external_groups`` and
        reconcile. Idempotent — a login with an unchanged group set is a no-op."""
        await self._s.rollback()
        wanted_keys = await self._roles_for_groups(provider, external_groups)
        wanted_ids = await self._role_ids(wanted_keys)

        current = {
            r[0]
            for r in (
                await self._s.execute(
                    select(ExternalRoleAssignment.role_id).where(
                        ExternalRoleAssignment.user_id == user_id,
                        ExternalRoleAssignment.provider == provider,
                    )
                )
            ).all()
        }
        to_add = wanted_ids - current
        to_remove = current - wanted_ids
        if not to_add and not to_remove:
            return

        by_id = {v: k for k, v in (await self._role_key_index()).items()}
        await self._s.rollback()  # close the read txs above before the write tx
        async with self._s.begin():
            for role_id in to_add:
                await self._s.execute(
                    pg_insert(UserRole)
                    .values(user_id=user_id, role_id=role_id, granted_by=None)
                    .on_conflict_do_nothing(index_elements=["user_id", "role_id"])
                )
                self._s.add(
                    ExternalRoleAssignment(user_id=user_id, role_id=role_id, provider=provider)
                )
                await AuditService(self._s).write(
                    AuditAction.USER_ROLE_ASSIGNED,
                    actor_user_id=None,
                    target_type="user",
                    target_id=str(user_id),
                    after={"role": by_id.get(role_id), "source": provider},
                )
            for role_id in to_remove:
                await self._s.execute(
                    delete(ExternalRoleAssignment).where(
                        ExternalRoleAssignment.user_id == user_id,
                        ExternalRoleAssignment.role_id == role_id,
                        ExternalRoleAssignment.provider == provider,
                    )
                )
                await self._s.execute(
                    delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
                )
                await AuditService(self._s).write(
                    AuditAction.USER_ROLE_REVOKED,
                    actor_user_id=None,
                    target_type="user",
                    target_id=str(user_id),
                    before={"role": by_id.get(role_id), "source": provider},
                )

    # --- helpers ----------------------------------------------

    async def _roles_for_groups(self, provider: str, groups: tuple[str, ...]) -> frozenset[str]:
        if not groups:
            return frozenset()
        rows = (
            await self._s.execute(
                select(AuthGroupMapping.role_key).where(
                    AuthGroupMapping.provider == provider,
                    AuthGroupMapping.external_group.in_(groups),
                )
            )
        ).scalars()
        return frozenset(rows)

    async def _role_key_index(self) -> dict[str, uuid.UUID]:
        rows = (await self._s.execute(select(Role.key, Role.id))).all()
        return {r.key: r.id for r in rows}

    async def _role_ids(self, keys: frozenset[str]) -> frozenset[uuid.UUID]:
        if not keys:
            return frozenset()
        index = await self._role_key_index()
        return frozenset(index[k] for k in keys if k in index)
