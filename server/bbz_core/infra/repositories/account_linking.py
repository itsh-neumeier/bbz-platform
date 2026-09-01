"""Account linking: a BBZ user can carry several ``auth_identities`` (roadmap E21-08).

Link a ``local`` password, an ``ldap_ad`` bind, or (via the OIDC link flow) an
``entra_oidc`` identity to the **already-logged-in** user. Unlinking is guarded:
never the last identity, and never one that would lock out the last active
admin. ``IDENTITY_LINKED`` / ``IDENTITY_UNLINKED`` audit.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.auth.hashing import hash_password
from bbz_core.auth.policy import PasswordPolicy
from bbz_core.infra.models.identity import AuthIdentity, LocalCredential
from bbz_core.infra.repositories.users_admin import UsersAdminRepository

_LINKABLE = {"local", "ldap_ad", "entra_oidc"}


class LinkingError(Exception):
    pass


class IdentityAlreadyLinked(LinkingError):
    """That (provider, subject) is already on another BBZ account."""


class ProviderAlreadyLinked(LinkingError):
    """This account already has an identity with that provider."""


class LastIdentityError(LinkingError):
    """Unlinking would leave the account with no way to sign in (or lock out the
    last admin)."""


class IdentityNotFound(LookupError):
    pass


@dataclass(frozen=True)
class IdentityView:
    id: uuid.UUID
    provider: str
    subject: str
    created_at: _dt.datetime


def _view(i: AuthIdentity) -> IdentityView:
    return IdentityView(id=i.id, provider=i.provider, subject=i.subject, created_at=i.created_at)


class AccountLinkingService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_identities(self, user_id: uuid.UUID) -> list[IdentityView]:
        await self._s.rollback()
        rows = (
            await self._s.execute(
                select(AuthIdentity)
                .where(AuthIdentity.user_id == user_id)
                .order_by(AuthIdentity.provider)
            )
        ).scalars()
        return [_view(i) for i in rows]

    async def link_local(
        self, user_id: uuid.UUID, *, username: str, password: str, actor_id: uuid.UUID
    ) -> IdentityView:
        await self._ensure_no_provider(user_id, "local")
        await self._ensure_subject_free("local", username)
        PasswordPolicy.from_settings().validate(password, username=username)
        await self._s.rollback()
        async with self._s.begin():
            ident = AuthIdentity(user_id=user_id, provider="local", subject=username)
            self._s.add(ident)
            await self._s.flush()
            self._s.add(
                LocalCredential(auth_identity_id=ident.id, password_hash=hash_password(password))
            )
            view = _view(ident)
            await self._audit_link(user_id, "local", username, actor_id)
        return view

    async def link_external(
        self, user_id: uuid.UUID, *, provider: str, subject: str, actor_id: uuid.UUID
    ) -> IdentityView:
        """Attach an already-verified external identity (``ldap_ad`` after a bind,
        ``entra_oidc`` after the OIDC link callback)."""
        if provider not in {"ldap_ad", "entra_oidc"}:
            raise LinkingError(f"not an external provider: {provider}")
        await self._ensure_no_provider(user_id, provider)
        await self._ensure_subject_free(provider, subject)
        await self._s.rollback()
        async with self._s.begin():
            ident = AuthIdentity(user_id=user_id, provider=provider, subject=subject)
            self._s.add(ident)
            await self._s.flush()
            view = _view(ident)
            await self._audit_link(user_id, provider, subject, actor_id)
        return view

    async def unlink(
        self, user_id: uuid.UUID, identity_id: uuid.UUID, *, actor_id: uuid.UUID
    ) -> None:
        await self._s.rollback()
        ident = await self._s.get(AuthIdentity, identity_id)
        if ident is None or ident.user_id != user_id:
            raise IdentityNotFound(str(identity_id))
        count = (
            await self._s.execute(
                select(func.count())
                .select_from(AuthIdentity)
                .where(AuthIdentity.user_id == user_id)
            )
        ).scalar_one()
        if count <= 1:
            raise LastIdentityError("cannot remove the account's only sign-in method")
        if await UsersAdminRepository(self._s)._is_last_active_admin(user_id):
            raise LastIdentityError("cannot reduce the last active administrator's sign-in methods")

        provider, subject = ident.provider, ident.subject
        await self._s.rollback()
        async with self._s.begin():
            fresh = await self._s.get(AuthIdentity, identity_id)
            if fresh is not None:
                await self._s.delete(fresh)  # cascades to credentials / TOTP / webauthn
            await AuditService(self._s).write(
                AuditAction.IDENTITY_UNLINKED,
                actor_user_id=actor_id,
                target_type="user",
                target_id=str(user_id),
                before={"provider": provider, "subject": subject},
            )

    # --- helpers -----------------------------------------------

    async def _ensure_no_provider(self, user_id: uuid.UUID, provider: str) -> None:
        await self._s.rollback()
        hit = (
            await self._s.execute(
                select(AuthIdentity.id).where(
                    AuthIdentity.user_id == user_id, AuthIdentity.provider == provider
                )
            )
        ).scalar_one_or_none()
        if hit is not None:
            raise ProviderAlreadyLinked(provider)

    async def _ensure_subject_free(self, provider: str, subject: str) -> None:
        await self._s.rollback()
        hit = (
            await self._s.execute(
                select(AuthIdentity.id).where(
                    AuthIdentity.provider == provider, AuthIdentity.subject == subject
                )
            )
        ).scalar_one_or_none()
        if hit is not None:
            raise IdentityAlreadyLinked(f"{provider}:{subject}")

    async def _audit_link(
        self, user_id: uuid.UUID, provider: str, subject: str, actor_id: uuid.UUID
    ) -> None:
        await AuditService(self._s).write(
            AuditAction.IDENTITY_LINKED,
            actor_user_id=actor_id,
            target_type="user",
            target_id=str(user_id),
            after={"provider": provider, "subject": subject},
        )
