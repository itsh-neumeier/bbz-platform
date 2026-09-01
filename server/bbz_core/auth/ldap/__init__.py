"""LDAP / Active Directory bind authentication (roadmap E21-03, MASTER_PROMPT §11).

Encrypted transport only (LDAPS or StartTLS), a service-account search followed
by a user bind, group resolution, and a failover server pool. ``ldap3`` is
synchronous — callers run :meth:`LdapClient.authenticate` in a worker thread.
"""

from __future__ import annotations

from bbz_core.auth.ldap.client import LdapClient, LdapPrincipal
from bbz_core.auth.ldap.config import LdapConfig
from bbz_core.auth.ldap.errors import (
    LdapAuthFailed,
    LdapConfigError,
    LdapError,
    LdapInsecureError,
    LdapUnavailableError,
)

__all__ = [
    "LdapAuthFailed",
    "LdapClient",
    "LdapConfig",
    "LdapConfigError",
    "LdapError",
    "LdapInsecureError",
    "LdapPrincipal",
    "LdapUnavailableError",
]
