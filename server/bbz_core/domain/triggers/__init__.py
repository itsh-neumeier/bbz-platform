"""Pure trigger-engine domain vocabulary (no I/O).

Typed action kinds for trigger rules (E15-03..08) and which of them are
delivered through the transactional outbox vs. run inside the triggering
transaction. Conditions/DSL evaluation is E15-05; the engine is E15-09.
"""

from __future__ import annotations

from bbz_core.domain.triggers.actions import (
    OUTBOX_ACTION_TYPES,
    SUPPORTED_ACTION_TYPES,
    TRANSACTIONAL_ACTION_TYPES,
    TriggerActionType,
    outbox_action_type,
)
from bbz_core.domain.triggers.alarms import (
    DERIVED_ID_PREFIX,
    AlarmEventRejected,
    alarm_event_dedupe_key,
    normalize_alarm_event,
)
from bbz_core.domain.triggers.rules import (
    CandidateRule,
    RuleConditionError,
    publish_blockers,
    rule_matches,
    select_matching_rules,
    signal_to_context,
    validate_actions,
    validate_conditions,
)
from bbz_core.domain.triggers.signals import (
    InboundSignalRejected,
    InboundSignalType,
    from_telephony_event,
    validate_inbound_signal,
)

__all__ = [
    "DERIVED_ID_PREFIX",
    "OUTBOX_ACTION_TYPES",
    "SUPPORTED_ACTION_TYPES",
    "TRANSACTIONAL_ACTION_TYPES",
    "AlarmEventRejected",
    "CandidateRule",
    "InboundSignalRejected",
    "InboundSignalType",
    "RuleConditionError",
    "TriggerActionType",
    "alarm_event_dedupe_key",
    "from_telephony_event",
    "normalize_alarm_event",
    "outbox_action_type",
    "publish_blockers",
    "rule_matches",
    "select_matching_rules",
    "signal_to_context",
    "validate_actions",
    "validate_conditions",
    "validate_inbound_signal",
]
