"""MFA policy: role → MFA-required, with a grace period (roadmap E21-05).

A user requires MFA if they hold **any** policy'd role, direct or via a group.
The grace deadline is the earliest ``(grant time + grace_period_days)`` across
every policy'd role the user holds — once any of those has elapsed, the user
has had time to enrol.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.models.mfa_policy import MfaPolicy
from bbz_core.infra.models.rbac import GroupRole, Role, UserGroup, UserRole


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class UnknownRoleKey(ValueError):
    pass


class PolicyNotFound(LookupError):
    pass


@dataclass(frozen=True)
class MfaPolicyView:
    role_key: str
    grace_period_days: int


@dataclass(frozen=True)
class MfaRequirement:
    required: bool
    in_grace: bool
    grace_until: _dt.datetime | None

    def blocks(self, *, satisfied: bool) -> bool:
        """True when the user must be refused: MFA is required, not satisfied,
        and the grace period (if any) has elapsed."""
        return self.required and not satisfied and not self.in_grace


_NOT_REQUIRED = MfaRequirement(required=False, in_grace=False, grace_until=None)


class MfaPolicyService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- CRUD (permissions.manage) --------------------------------

    async def list_policies(self) -> list[MfaPolicyView]:
        rows = (await self._s.execute(select(MfaPolicy).order_by(MfaPolicy.role_key))).scalars()
        return [MfaPolicyView(p.role_key, p.grace_period_days) for p in rows]

    async def set_policy(
        self, role_key: str, *, grace_period_days: int, actor_id: uuid.UUID | None
    ) -> MfaPolicyView:
        await self._s.rollback()
        async with self._s.begin():
            exists = (
                await self._s.execute(select(Role.id).where(Role.key == role_key))
            ).scalar_one_or_none()
            if exists is None:
                raise UnknownRoleKey(role_key)
            before = await self._s.get(MfaPolicy, role_key)
            await self._s.execute(
                pg_insert(MfaPolicy)
                .values(role_key=role_key, grace_period_days=grace_period_days, created_by=actor_id)
                .on_conflict_do_update(
                    index_elements=["role_key"],
                    set_={"grace_period_days": grace_period_days, "updated_at": _now()},
                )
            )
            await AuditService(self._s).write(
                AuditAction.MFA_POLICY_CHANGED,
                actor_user_id=actor_id,
                target_type="mfa_policy",
                target_id=role_key,
                before=None if before is None else {"grace_period_days": before.grace_period_days},
                after={"grace_period_days": grace_period_days, "op": "set"},
            )
        return MfaPolicyView(role_key, grace_period_days)

    async def delete_policy(self, role_key: str, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        async with self._s.begin():
            row = await self._s.get(MfaPolicy, role_key)
            if row is None:
                raise PolicyNotFound(role_key)
            before = {"grace_period_days": row.grace_period_days}
            await self._s.delete(row)
            await AuditService(self._s).write(
                AuditAction.MFA_POLICY_CHANGED,
                actor_user_id=actor_id,
                target_type="mfa_policy",
                target_id=role_key,
                before=before,
                after={"op": "delete"},
            )

    # --- evaluation (login + step-up) ------------------------------

    async def evaluate(self, user_id: uuid.UUID) -> MfaRequirement:
        # read-only — no rollback/begin here (a rollback would expire the
        # caller's freshly-loaded ORM objects mid-login)
        policies = {
            p.role_key: p.grace_period_days
            for p in (await self._s.execute(select(MfaPolicy))).scalars()
        }
        if not policies:
            return _NOT_REQUIRED

        direct = (
            await self._s.execute(
                select(Role.key, UserRole.granted_at)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(UserRole.user_id == user_id, Role.key.in_(policies))
            )
        ).all()
        via_group = (
            await self._s.execute(
                select(Role.key, UserGroup.added_at)
                .select_from(UserGroup)
                .join(GroupRole, GroupRole.group_id == UserGroup.group_id)
                .join(Role, Role.id == GroupRole.role_id)
                .where(UserGroup.user_id == user_id, Role.key.in_(policies))
            )
        ).all()
        grants = list(direct) + list(via_group)
        if not grants:
            return _NOT_REQUIRED

        deadline = min(
            granted_at + _dt.timedelta(days=policies[role_key]) for role_key, granted_at in grants
        )
        now = _now()
        return MfaRequirement(required=True, in_grace=now < deadline, grace_until=deadline)
