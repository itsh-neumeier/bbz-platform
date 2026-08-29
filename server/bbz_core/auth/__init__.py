"""Provider-based authentication.

Roadmap E02-03 (local passwords) + E02-04 (provider contract). Session
issuance is E02-05; permission checks E02-06; MFA/OIDC/LDAP Epic 21.
"""

from __future__ import annotations

from bbz_core.auth.hashing import hash_password, needs_rehash, verify_password
from bbz_core.auth.local import (
    AuthOutcome,
    CredentialRecord,
    CredentialStore,
    LocalAuthResult,
    LocalAuthService,
)
from bbz_core.auth.policy import PasswordPolicy, PasswordPolicyError
from bbz_core.auth.provider import (
    AuthenticatedIdentity,
    AuthProvider,
    CredentialKind,
    IdentityResolver,
    PasswordAuthOutcome,
    PasswordAuthProvider,
    ProviderCapabilities,
)
from bbz_core.auth.providers import (
    EntraOidcAuthProvider,
    LdapAdAuthProvider,
    LocalAuthProvider,
    LocalIdentityStore,
)
from bbz_core.auth.registry import AuthProviderRegistry, UnknownAuthProviderError

__all__ = [
    "AuthOutcome",
    "AuthProvider",
    "AuthProviderRegistry",
    "AuthenticatedIdentity",
    "CredentialKind",
    "CredentialRecord",
    "CredentialStore",
    "EntraOidcAuthProvider",
    "IdentityResolver",
    "LdapAdAuthProvider",
    "LocalAuthProvider",
    "LocalAuthResult",
    "LocalAuthService",
    "LocalIdentityStore",
    "PasswordAuthOutcome",
    "PasswordAuthProvider",
    "PasswordPolicy",
    "PasswordPolicyError",
    "ProviderCapabilities",
    "UnknownAuthProviderError",
    "hash_password",
    "needs_rehash",
    "verify_password",
]
