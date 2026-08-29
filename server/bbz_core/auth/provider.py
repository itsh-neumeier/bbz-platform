"""Provider-based authentication contract.

MASTER_PROMPT §11 / roadmap E02-04. Every authentication source (local
passwords, Entra OIDC, LDAP/AD) is an :class:`AuthProvider`. Only ``local`` is
implemented here; external providers are honest ``NotImplementedError`` stubs
with their capability flags set (Epic 21 fills them in).

Credential *verification* is provider-shaped (a password vs. an OIDC redirect
vs. an LDAP bind), so it is not forced into one signature. What every provider
shares — capability discovery and ``subject`` → identity resolution — is the
Protocol. Password providers additionally satisfy :class:`PasswordAuthProvider`.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from bbz_core.auth.local import LocalAuthResult


class CredentialKind(enum.StrEnum):
    PASSWORD = "password"
    EXTERNAL_REDIRECT = "external_redirect"  # OIDC authorization-code flow
    DIRECTORY_BIND = "directory_bind"  # LDAP simple bind


@dataclass(frozen=True)
class ProviderCapabilities:
    credential_kind: CredentialKind
    interactive_login: bool = True
    password_change: bool = False
    directory_sync: bool = False
    mfa_totp: bool = False


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """A verified external/local principal, before it is linked to a BBZ user."""

    provider: str
    subject: str
    display_name: str | None = None
    groups: tuple[str, ...] = ()
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PasswordAuthOutcome:
    result: LocalAuthResult
    identity: AuthenticatedIdentity | None = None
    user_id: uuid.UUID | None = None
    must_change_password: bool = False


@runtime_checkable
class AuthProvider(Protocol):
    name: str

    def capabilities(self) -> ProviderCapabilities: ...

    async def get_identity(self, subject: str) -> AuthenticatedIdentity | None:
        """Resolve a provider ``subject`` to its current identity, or None."""
        ...


@runtime_checkable
class PasswordAuthProvider(AuthProvider, Protocol):
    async def authenticate_password(self, username: str, password: str) -> PasswordAuthOutcome: ...


class IdentityResolver(Protocol):
    """Maps a verified :class:`AuthenticatedIdentity` to a BBZ ``user_id``.

    ``provision=True`` allows just-in-time user creation for external providers
    (policy lives in Epic 21). For ``local`` the identity always pre-exists.
    """

    async def resolve(
        self, identity: AuthenticatedIdentity, *, provision: bool
    ) -> uuid.UUID | None: ...
