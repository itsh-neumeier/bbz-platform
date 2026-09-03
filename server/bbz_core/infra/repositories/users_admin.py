"""Write-side repository for user administration (E02-10).

Local-account lifecycle: create (optionally with a local login), rename,
activate / deactivate (deactivation revokes every live session), and an
administrative password reset that forces a change on next login.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Select, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.auth.hashing import hash_password
from bbz_core.auth.policy import PasswordPolicy
from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User, UserStatus
from bbz_core.infra.models.rbac import (
    GroupRole,
    Permission,
    Role,
    RolePermission,
    UserGroup,
    UserRole,
)
from bbz_core.infra.models.session import Session


class UsersAdminError(Exception):
    pass


class LastAdminError(UsersAdminError):
    pass


class UsernameTakenError(UsersAdminError):
    pass


@dataclass(frozen=True)
class NewUser:
    display_name: str
    external_ref: str | None = None
    local_username: str | None = None
    initial_password: str | None = None


class UsersAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_users(self, *, include_disabled: bool = True) -> Sequence[User]:
        stmt = select(User).order_by(User.display_name)
        if not include_disabled:
            stmt = stmt.where(User.status == UserStatus.ACTIVE.value)
        return (await self._s.execute(stmt)).scalars().all()

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._s.get(User, user_id)

    async def roles_by_user(
        self, user_ids: Sequence[uuid.UUID] | None = None
    ) -> dict[uuid.UUID, list[str]]:
        """``{user_id: [role_key, ...]}`` — directly-granted roles only (group
        roles are effective but not shown as the user's own)."""
        stmt = select(UserRole.user_id, Role.key).join(Role, Role.id == UserRole.role_id)
        if user_ids is not None:
            stmt = stmt.where(UserRole.user_id.in_(user_ids))
        out: dict[uuid.UUID, list[str]] = {}
        for uid, key in (await self._s.execute(stmt)).all():
            out.setdefault(uid, []).append(key)
        for keys in out.values():
            keys.sort()
        return out

    async def providers_by_user(
        self, user_ids: Sequence[uuid.UUID] | None = None
    ) -> dict[uuid.UUID, list[str]]:
        """``{user_id: [provider, ...]}`` from ``auth_identities`` (local / ldap_ad / oidc / …)."""
        stmt = select(AuthIdentity.user_id, AuthIdentity.provider).distinct()
        if user_ids is not None:
            stmt = stmt.where(AuthIdentity.user_id.in_(user_ids))
        out: dict[uuid.UUID, list[str]] = {}
        for uid, provider in (await self._s.execute(stmt)).all():
            out.setdefault(uid, []).append(provider)
        for provs in out.values():
            provs.sort()
        return out

    async def create(self, spec: NewUser) -> User:
        if spec.local_username and await self._local_username_taken(spec.local_username):
            raise UsernameTakenError(spec.local_username)
        user = User(display_name=spec.display_name, external_ref=spec.external_ref)
        self._s.add(user)
        await self._s.flush()
        if spec.local_username:
            ident = AuthIdentity(user_id=user.id, provider="local", subject=spec.local_username)
            self._s.add(ident)
            await self._s.flush()
            if spec.initial_password:
                PasswordPolicy.from_settings().validate(
                    spec.initial_password, username=spec.local_username
                )
                self._s.add(
                    LocalCredential(
                        auth_identity_id=ident.id,
                        password_hash=hash_password(spec.initial_password),
                        must_change=True,
                    )
                )
        await self._s.commit()
        return user

    async def update(
        self, user: User, *, display_name: str | None, external_ref: str | None
    ) -> User:
        if display_name is not None:
            user.display_name = display_name
        if external_ref is not None:
            user.external_ref = external_ref or None
        await self._s.commit()
        return user

    async def set_active(
        self, user: User, *, active: bool, actor_id: uuid.UUID | None = None
    ) -> int:
        """Returns the number of sessions revoked (0 when activating). A real
        active→disabled transition audits ``USER_DEACTIVATED`` (a critical action)."""
        if not active and await self._is_last_active_admin(user.id):
            raise LastAdminError("cannot deactivate the last user able to manage permissions")
        was_active = user.status == UserStatus.ACTIVE.value
        user.status = (UserStatus.ACTIVE if active else UserStatus.DISABLED).value
        revoked = 0
        if not active:
            revoked = await self._revoke_sessions(user.id)
            if was_active:
                await AuditService(self._s).write(
                    AuditAction.USER_DEACTIVATED,
                    actor_user_id=actor_id,
                    target_type="user",
                    target_id=str(user.id),
                    before={"status": UserStatus.ACTIVE.value},
                    after={"status": UserStatus.DISABLED.value, "sessions_revoked": revoked},
                )
        await self._s.commit()
        return revoked

    async def reset_password(self, user: User, new_password: str) -> int:
        ident = (
            await self._s.execute(
                select(AuthIdentity).where(
                    AuthIdentity.user_id == user.id, AuthIdentity.provider == "local"
                )
            )
        ).scalar_one_or_none()
        if ident is None:
            raise UsersAdminError("user has no local login")
        PasswordPolicy.from_settings().validate(new_password, username=ident.subject)
        cred = await self._s.get(LocalCredential, ident.id)
        new_hash = hash_password(new_password)
        if cred is None:
            self._s.add(
                LocalCredential(auth_identity_id=ident.id, password_hash=new_hash, must_change=True)
            )
        else:
            cred.password_hash = new_hash
            cred.must_change = True
            cred.failed_attempts = 0
            cred.locked_until = None
        revoked = await self._revoke_sessions(user.id)
        await self._s.commit()
        return revoked

    # --- helpers -----------------------------------------------------

    async def _local_username_taken(self, username: str) -> bool:
        return bool(
            await self._s.scalar(
                select(
                    exists().where(
                        AuthIdentity.provider == "local", AuthIdentity.subject == username
                    )
                )
            )
        )

    async def _revoke_sessions(self, user_id: uuid.UUID) -> int:
        from datetime import UTC, datetime

        from sqlalchemy import update

        result = await self._s.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    @staticmethod
    def _admin_role_ids() -> Select[tuple[uuid.UUID]]:
        return (
            select(RolePermission.role_id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(Permission.key == "permissions.manage")
        )

    async def _holds_admin(self, user_id: uuid.UUID) -> bool:
        roles = self._admin_role_ids()
        direct = select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id.in_(roles))
        via_group = (
            select(UserGroup)
            .join(GroupRole, GroupRole.group_id == UserGroup.group_id)
            .where(UserGroup.user_id == user_id, GroupRole.role_id.in_(roles))
        )
        return bool(await self._s.scalar(select(exists(direct)))) or bool(
            await self._s.scalar(select(exists(via_group)))
        )

    async def _is_last_active_admin(self, user_id: uuid.UUID) -> bool:
        if not await self._holds_admin(user_id):
            return False
        roles = self._admin_role_ids()
        direct = select(UserRole.user_id).where(UserRole.role_id.in_(roles))
        via_group = (
            select(UserGroup.user_id)
            .join(GroupRole, GroupRole.group_id == UserGroup.group_id)
            .where(GroupRole.role_id.in_(roles))
        )
        admin_ids = direct.union(via_group).subquery()
        other_active = await self._s.scalar(
            select(func.count(func.distinct(User.id))).where(
                User.id.in_(select(admin_ids.c[0])),
                User.status == UserStatus.ACTIVE.value,
                User.id != user_id,
            )
        )
        return (other_active or 0) == 0
