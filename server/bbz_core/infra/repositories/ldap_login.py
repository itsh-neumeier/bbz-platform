"""LDAP / AD login orchestration (roadmap E21-03).

Runs the (blocking) bind auth in a worker thread, maps the directory principal to
a BBZ user (JIT-optional), reconciles group-mapped roles (shared with OIDC,
E21-02), and audits the outcome. Local password login is tried first by the API;
this is the fallback for directory accounts.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.auth.ldap import (
    LdapAuthFailed,
    LdapClient,
    LdapConfig,
    LdapConfigError,
    LdapError,
    LdapPrincipal,
)
from bbz_core.infra.models.identity import AuthIdentity, User
from bbz_core.infra.models.rbac import Role, UserRole
from bbz_core.settings import get_settings

_PROVIDER = "ldap_ad"


def config_from_settings() -> LdapConfig:
    s = get_settings()
    if not s.ldap_url or not s.ldap_bind_dn or not s.ldap_user_search_base:
        raise LdapConfigError("ldap_url / ldap_bind_dn / ldap_user_search_base not set")
    return LdapConfig(
        urls=tuple(u.strip() for u in s.ldap_url.split(",") if u.strip()),
        bind_dn=s.ldap_bind_dn,
        bind_password=s.ldap_bind_password,
        user_search_base=s.ldap_user_search_base,
        user_filter=s.ldap_user_filter,
        user_list_filter=s.ldap_user_list_filter,
        page_size=s.ldap_page_size,
        group_search_base=s.ldap_group_search_base,
        group_filter=s.ldap_group_filter,
        uid_attr=s.ldap_uid_attr,
        name_attr=s.ldap_name_attr,
        mail_attr=s.ldap_mail_attr,
        start_tls=s.ldap_start_tls,
        tls_verify=s.ldap_tls_verify,
        tls_ca_file=s.ldap_tls_ca_file,
    )


class LdapLoginService:
    def __init__(self, session: AsyncSession, *, client: LdapClient | None = None) -> None:
        self._s = session
        self._client = client

    async def authenticate(
        self,
        username: str,
        password: str,
        *,
        client_id: str | None = None,
        workplace_id: str | None = None,
    ) -> uuid.UUID:
        """Bind-authenticate, resolve to a BBZ user, sync roles. Audits
        ``LOGIN_SUCCEEDED`` / ``LOGIN_FAILED``."""
        client = self._client or LdapClient(config_from_settings())
        try:
            principal = await asyncio.to_thread(client.authenticate, username, password)
            user_id = await self._resolve_user(principal)
            await self._sync_roles(user_id, principal)
        except LdapError as exc:
            await self._audit_failed(username, reason=type(exc).__name__, client_id=client_id)
            raise
        await self._audit_ok(user_id, client_id=client_id, workplace_id=workplace_id)
        return user_id

    # --- steps -------------------------------------------------

    async def _resolve_user(self, principal: LdapPrincipal) -> uuid.UUID:
        await self._s.rollback()
        existing = (
            await self._s.execute(
                select(AuthIdentity).where(
                    AuthIdentity.provider == _PROVIDER, AuthIdentity.subject == principal.uid
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing.user_id

        if not get_settings().ldap_jit_provisioning:
            raise LdapAuthFailed("directory user is not provisioned in BBZ")

        default_role = get_settings().oidc_jit_default_role.strip()
        await self._s.rollback()
        async with self._s.begin():
            user = User(display_name=principal.display_name or principal.email or principal.uid)
            self._s.add(user)
            await self._s.flush()
            self._s.add(AuthIdentity(user_id=user.id, provider=_PROVIDER, subject=principal.uid))
            if default_role:
                rid = (
                    await self._s.execute(select(Role.id).where(Role.key == default_role))
                ).scalar_one_or_none()
                if rid is not None:
                    self._s.add(UserRole(user_id=user.id, role_id=rid, granted_by=None))
        return user.id

    async def _sync_roles(self, user_id: uuid.UUID, principal: LdapPrincipal) -> None:
        from bbz_core.infra.repositories.auth_group_mapping import GroupMappingService

        await GroupMappingService(self._s).sync_user_roles(
            user_id=user_id, provider=_PROVIDER, external_groups=principal.groups
        )

    async def _audit_ok(
        self, user_id: uuid.UUID, *, client_id: str | None, workplace_id: str | None
    ) -> None:
        await self._s.rollback()
        async with self._s.begin():
            await AuditService(self._s).write(
                AuditAction.LOGIN_SUCCEEDED,
                actor_user_id=user_id,
                actor_client_id=client_id,
                workplace_id=workplace_id,
                target_type="login_attempt",
                after={"provider": _PROVIDER},
            )

    async def _audit_failed(self, username: str, *, reason: str, client_id: str | None) -> None:
        await self._s.rollback()
        async with self._s.begin():
            await AuditService(self._s).write(
                AuditAction.LOGIN_FAILED,
                actor_client_id=client_id,
                target_type="login_attempt",
                target_id=username[:64],
                after={"provider": _PROVIDER, "reason": reason},
            )
