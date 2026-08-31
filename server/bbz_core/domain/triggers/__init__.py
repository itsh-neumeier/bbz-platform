"""Pure trigger-engine domain vocabulary (no I/O).

Typed action kinds for trigger rules (E15-03..08) and which of them are
delivered through the transactional outbox vs. run inside the triggering
transaction. Conditions/DSL evaluation is E15-05; the engine is E15-09.
"""

from __future__ import annotations

from bbz_core.domain.triggers.actions import (
    OUTBOX_ACTION_TYPES,
    TRANSACTIONAL_ACTION_TYPES,
    TriggerActionType,
    outbox_action_type,
)
from bbz_core.domain.triggers.signals import (
    InboundSignalRejected,
    InboundSignalType,
    from_telephony_event,
    validate_inbound_signal,
)

__all__ = [
    "OUTBOX_ACTION_TYPES",
    "TRANSACTIONAL_ACTION_TYPES",
    "InboundSignalRejected",
    "InboundSignalType",
    "TriggerActionType",
    "from_telephony_event",
    "outbox_action_type",
    "validate_inbound_signal",
]
