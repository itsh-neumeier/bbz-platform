"""ORM models for the BBZ core.

Importing this package pulls in every model so that ``Base.metadata`` is
complete - used by Alembic (``target_metadata``) and by tests.
"""

from __future__ import annotations

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.base import Base
from bbz_core.infra.models.commands import Command
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import (
    Event,
    EventAssignment,
    EventNote,
    EventNoteKind,
    EventPriority,
    EventStatus,
    EventStatusHistory,
)
from bbz_core.infra.models.identity import (
    AuthIdentity,
    AuthProvider,
    LocalCredential,
    LocalTotp,
    LocalTotpRecoveryCode,
    PresenceState,
    User,
    UserPresence,
    UserStatus,
)
from bbz_core.infra.models.outbox import ExternalActionOutbox, OutboxStatus
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
    "AuditEvent",
    "AuthIdentity",
    "AuthProvider",
    "Base",
    "Command",
    "DomainEvent",
    "Event",
    "EventAssignment",
    "EventNote",
    "EventNoteKind",
    "EventPriority",
    "EventStatus",
    "EventStatusHistory",
    "ExternalActionOutbox",
    "Group",
    "GroupRole",
    "LocalCredential",
    "LocalTotp",
    "LocalTotpRecoveryCode",
    "OutboxStatus",
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
