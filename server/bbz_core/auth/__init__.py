"""Local authentication: Argon2id hashing, password policy, lockout.

Roadmap E02-03. This module authenticates *local* users only. External
providers (OIDC/LDAP) and the shared ``AuthProvider`` protocol arrive in
E02-04 / Epic 21. Session issuance is E02-05.
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

__all__ = [
    "AuthOutcome",
    "CredentialRecord",
    "CredentialStore",
    "LocalAuthResult",
    "LocalAuthService",
    "PasswordPolicy",
    "PasswordPolicyError",
    "hash_password",
    "needs_rehash",
    "verify_password",
]
