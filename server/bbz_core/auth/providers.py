"""Concrete auth providers: ``local`` (real) and OIDC / LDAP (stubs)."""

from __future__ import annotations

import uuid
from typing import Protocol

from bbz_core.auth.local import CredentialStore, LocalAuthResult, LocalAuthService
from bbz_core.auth.provider import (
    AuthenticatedIdentity,
    CredentialKind,
    IdentityResolver,
    PasswordAuthOutcome,
    ProviderCapabilities,
)


class LocalIdentityStore(CredentialStore, IdentityResolver, Protocol):
    """Superset the local provider needs: credential store + identity resolution."""

    async def get_identity(self, subject: str) -> AuthenticatedIdentity | None: ...


class LocalAuthProvider:
    name = "local"

    def __init__(self, store: LocalIdentityStore, service: LocalAuthService | None = None) -> None:
        self._store = store
        self._service = service or LocalAuthService(store)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            credential_kind=CredentialKind.PASSWORD,
            interactive_login=True,
            password_change=True,
            directory_sync=False,
            mfa_totp=True,  # E02-13 adds the TOTP check into this provider
        )

    async def get_identity(self, subject: str) -> AuthenticatedIdentity | None:
        return await self._store.get_identity(subject)

    async def authenticate_password(self, username: str, password: str) -> PasswordAuthOutcome:
        out = await self._service.authenticate(username, password)
        identity = (
            AuthenticatedIdentity(provider="local", subject=username)
            if out.result is LocalAuthResult.SUCCESS
            else None
        )
        return PasswordAuthOutcome(
            result=out.result,
            identity=identity,
            user_id=out.user_id,
            must_change_password=out.must_change_password,
        )


class _ExternalStub:
    """Shared body for the not-yet-implemented external providers (Epic 21)."""

    name = "external"
    _kind = CredentialKind.EXTERNAL_REDIRECT

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            credential_kind=self._kind,
            interactive_login=True,
            directory_sync=True,
        )

    async def get_identity(self, subject: str) -> AuthenticatedIdentity | None:
        raise NotImplementedError(f"{self.name} auth provider is not implemented yet (Epic 21)")

    async def resolve(
        self, identity: AuthenticatedIdentity, *, provision: bool
    ) -> uuid.UUID | None:
        raise NotImplementedError(f"{self.name} provisioning is not implemented yet (Epic 21)")


class EntraOidcAuthProvider(_ExternalStub):
    name = "entra_oidc"
    _kind = CredentialKind.EXTERNAL_REDIRECT


class LdapAdAuthProvider(_ExternalStub):
    name = "ldap_ad"
    _kind = CredentialKind.DIRECTORY_BIND
