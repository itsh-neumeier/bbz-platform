"""ORM models for the BBZ core.

Importing this package pulls in every model so that ``Base.metadata`` is
complete - used by Alembic (``target_metadata``) and by tests.
"""

from __future__ import annotations

from bbz_core.infra.models.application_catalog import (
    ApplicationCatalogEntry,
    ApplicationCatalogScope,
    LaunchMode,
)
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.auth_mapping import AuthGroupMapping, ExternalRoleAssignment
from bbz_core.infra.models.base import Base
from bbz_core.infra.models.bku_agent import (
    BkuAgent,
    BkuAgentCommand,
    BkuAgentEnrollment,
    BkuAgentStatus,
    BkuCommandStatus,
    BkuCommandType,
)
from bbz_core.infra.models.client_popup_events import ClientPopupEvent
from bbz_core.infra.models.commands import Command
from bbz_core.infra.models.contacts import (
    Contact,
    ContactNumber,
    ContactPriority,
    ContactPriorityLevel,
)
from bbz_core.infra.models.directory_sync import DirectorySyncState
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.door_action_profiles import DoorActionProfile
from bbz_core.infra.models.door_open_commands import (
    DoorOpenCommand,
    DoorOpenOutcome,
    DoorOpenState,
)
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
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.integration_camera_mappings import IntegrationCameraMapping
from bbz_core.infra.models.mfa_policy import MfaPolicy
from bbz_core.infra.models.monitor import (
    MonitorInput,
    MonitorOutput,
    MonitorProfile,
    MonitorProfileScope,
    MonitorRoute,
)
from bbz_core.infra.models.oidc import OidcLoginFlow
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
from bbz_core.infra.models.technical_endpoints import (
    TechnicalEndpoint,
    TechnicalEndpointNumber,
    TechnicalEndpointType,
)
from bbz_core.infra.models.telephony import (
    Call,
    CallCategory,
    CallDirection,
    CallDocumentation,
    CallParticipant,
    CallState,
    Line,
    LineState,
    ParticipantRole,
)
from bbz_core.infra.models.trigger_rules import (
    TriggerExecution,
    TriggerExecutionStatus,
    TriggerLifecycle,
    TriggerRule,
    TriggerRuleVersion,
)
from bbz_core.infra.models.unmapped_signals import UnmappedSignal
from bbz_core.infra.models.weather import WeatherAlert, WeatherObservation
from bbz_core.infra.models.weather_alert_events import WeatherAlertEvent
from bbz_core.infra.models.weather_refresh import WeatherRefreshState
from bbz_core.infra.models.workflow import (
    WorkflowGraphEdge,
    WorkflowGraphNode,
    WorkflowLifecycle,
    WorkflowTemplate,
    WorkflowTemplateVersion,
)
from bbz_core.infra.models.workflow_runtime import (
    WorkflowDecision,
    WorkflowInstance,
    WorkflowInstanceStatus,
    WorkflowTaskResult,
    WorkflowToken,
    WorkflowTokenState,
)

__all__ = [
    "ApplicationCatalogEntry",
    "ApplicationCatalogScope",
    "AuditEvent",
    "AuthGroupMapping",
    "AuthIdentity",
    "AuthProvider",
    "Base",
    "BkuAgent",
    "BkuAgentCommand",
    "BkuAgentEnrollment",
    "BkuAgentStatus",
    "BkuCommandStatus",
    "BkuCommandType",
    "Call",
    "CallCategory",
    "CallDirection",
    "CallDocumentation",
    "CallParticipant",
    "CallState",
    "ClientPopupEvent",
    "Command",
    "Contact",
    "ContactNumber",
    "ContactPriority",
    "ContactPriorityLevel",
    "DirectorySyncState",
    "DomainEvent",
    "DoorActionProfile",
    "DoorOpenCommand",
    "DoorOpenOutcome",
    "DoorOpenState",
    "Event",
    "EventAssignment",
    "EventNote",
    "EventNoteKind",
    "EventPriority",
    "EventStatus",
    "EventStatusHistory",
    "ExternalActionOutbox",
    "ExternalRoleAssignment",
    "Group",
    "GroupRole",
    "IntegrationCameraMapping",
    "LaunchMode",
    "Line",
    "LineState",
    "LocalCredential",
    "LocalTotp",
    "LocalTotpRecoveryCode",
    "MfaPolicy",
    "MonitorInput",
    "MonitorOutput",
    "MonitorProfile",
    "MonitorProfileScope",
    "MonitorRoute",
    "OidcLoginFlow",
    "OutboxStatus",
    "ParticipantRole",
    "Permission",
    "PresenceState",
    "ProviderEventInbox",
    "Role",
    "RolePermission",
    "Scope",
    "Session",
    "TechnicalEndpoint",
    "TechnicalEndpointNumber",
    "TechnicalEndpointType",
    "TriggerExecution",
    "TriggerExecutionStatus",
    "TriggerLifecycle",
    "TriggerRule",
    "TriggerRuleVersion",
    "UnmappedSignal",
    "User",
    "UserGroup",
    "UserPresence",
    "UserRole",
    "UserStatus",
    "WeatherAlert",
    "WeatherAlertEvent",
    "WeatherObservation",
    "WeatherRefreshState",
    "WorkflowDecision",
    "WorkflowGraphEdge",
    "WorkflowGraphNode",
    "WorkflowInstance",
    "WorkflowInstanceStatus",
    "WorkflowLifecycle",
    "WorkflowTaskResult",
    "WorkflowTemplate",
    "WorkflowTemplateVersion",
    "WorkflowToken",
    "WorkflowTokenState",
]
