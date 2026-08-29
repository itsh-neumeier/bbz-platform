"""ORM models for the BBZ core.

Importing this package pulls in every model so that ``Base.metadata`` is
complete — used by Alembic (``target_metadata``) and by tests.
"""

from __future__ import annotations

from bbz_core.infra.models.base import Base
from bbz_core.infra.models.identity import (
    AuthIdentity,
    AuthProvider,
    PresenceState,
    User,
    UserPresence,
    UserStatus,
)

__all__ = [
    "AuthIdentity",
    "AuthProvider",
    "Base",
    "PresenceState",
    "User",
    "UserPresence",
    "UserStatus",
]
