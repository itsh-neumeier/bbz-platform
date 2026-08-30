"""Telephony domain: the pure call aggregate + lifecycle state machine (E11-04)."""

from __future__ import annotations

from bbz_core.domain.telephony.call import CallAggregate, CallDomainEvent
from bbz_core.domain.telephony.state import (
    TERMINAL,
    CallDirection,
    CallState,
    business_event_for,
    provider_target_state,
)

__all__ = [
    "TERMINAL",
    "CallAggregate",
    "CallDirection",
    "CallDomainEvent",
    "CallState",
    "business_event_for",
    "provider_target_state",
]
