"""ORM models for the BBZ core.

Importing this package pulls in every model so that ``Base.metadata`` is
complete - used by Alembic (``target_metadata``) and by tests.
"""

from __future__ import annotations

from bbz_core.infra.models.base import Base
from bbz_core.infra.models.identity import (
    AuthIdentity,
    AuthProvider,
    LocalCredential,
    PresenceState,
    User,
    UserPresence,
    UserStatus,
)
from bbz_core.infra.models.rbac import (
    Group,
    GroupRole,
    Permission,
    Role,
    RolePermission,
    Scope,
    UserGroup,
    UserRole,
)
from bbz_core.infra.models.session import Session

__all__ = [
    "AuthIdentity",
    "AuthProvider",
    "Base",
    "Group",
    "GroupRole",
    "LocalCredential",
    "Permission",
    "PresenceState",
    "Role",
    "RolePermission",
    "Scope",
    "Session",
    "User",
    "UserGroup",
    "UserPresence",
    "UserRole",
    "UserStatus",
]
