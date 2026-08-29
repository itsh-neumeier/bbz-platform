"""Server-side authorization: the permission catalog, effective-permission
resolution and the ``authorize`` decision (roadmap E02-06..E02-08).

This package holds no I/O — it works against a store Protocol implemented in
``bbz_core.infra`` — so ``bbz_core.domain`` and it stay decoupled from storage.
"""

from __future__ import annotations

from bbz_core.authorization.keys import (
    CATALOG,
    PERMISSION_KEYS,
    SCOPES,
    PermissionKeyError,
    assert_known,
)
from bbz_core.authorization.model import EffectivePermissions, Grant
from bbz_core.authorization.resolver import ScopeContext, grant_resolves, scope_covers
from bbz_core.authorization.scopes import Scope
from bbz_core.authorization.service import GrantStore, PermissionService

__all__ = [
    "CATALOG",
    "PERMISSION_KEYS",
    "SCOPES",
    "EffectivePermissions",
    "Grant",
    "GrantStore",
    "PermissionKeyError",
    "PermissionService",
    "Scope",
    "ScopeContext",
    "assert_known",
    "grant_resolves",
    "scope_covers",
]
