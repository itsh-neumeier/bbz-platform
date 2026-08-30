"""Call lifecycle state machine (roadmap E11-04, MASTER_PROMPT §3/§8.4).

Pure. The aggregate consumes **normalized** telephony event names (the
``telephony_event.v1`` enum) and produces the platform's business call events
(``CALL_RINGING`` / ``CALL_ANSWERED`` / ``CALL_ENDED``).

The string values match ``bbz_core.infra.models.telephony.CallState`` /
``CallDirection`` — a test keeps the two in lock-step — but the domain layer
must not import infra, so it owns its own copy.
"""

from __future__ import annotations

from enum import StrEnum


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallState(StrEnum):
    OFFERED = "offered"
    RINGING = "ringing"
    CONNECTED = "connected"
    HELD = "held"
    TRANSFERRING = "transferring"
    DISCONNECTED = "disconnected"
    FAILED = "failed"
    #: hung up but not yet documented (E11-10) — set by the call service, never
    #: by a provider event
    ENDED_PENDING_DOCUMENTATION = "ended_pending_documentation"


TERMINAL: frozenset[CallState] = frozenset(
    {CallState.DISCONNECTED, CallState.FAILED, CallState.ENDED_PENDING_DOCUMENTATION}
)

#: normalized provider event -> the call state it drives the call to. Events not
#: in this map (LINE_*, DEVICE_*, CTI_*) are not call transitions.
_PROVIDER_TARGET: dict[str, CallState] = {
    "CALL_OFFERED": CallState.OFFERED,
    "CALL_RINGING": CallState.RINGING,
    "CALL_ANSWERED": CallState.CONNECTED,
    "CALL_CONNECTED": CallState.CONNECTED,
    "CALL_HELD": CallState.HELD,
    "CALL_RESUMED": CallState.CONNECTED,
    "CALL_TRANSFER_INITIATED": CallState.TRANSFERRING,
    "CALL_TRANSFERRED": CallState.CONNECTED,
    "CALL_CONFERENCED": CallState.CONNECTED,
    "CALL_DISCONNECTED": CallState.DISCONNECTED,
    "CALL_FAILED": CallState.FAILED,
}


def provider_target_state(normalized_event_type: str) -> CallState | None:
    return _PROVIDER_TARGET.get(normalized_event_type)


def business_event_for(old: CallState, new: CallState) -> str | None:
    """The business domain event a state change emits, if any (audit + log)."""
    if old is new:
        return None
    if new is CallState.RINGING and old in (CallState.OFFERED,):
        return "CALL_RINGING"
    if new is CallState.CONNECTED and old in (CallState.OFFERED, CallState.RINGING):
        return "CALL_ANSWERED"  # first connect only — resume-from-hold does not fire it
    if new in TERMINAL and old not in TERMINAL:
        return "CALL_ENDED"
    return None
