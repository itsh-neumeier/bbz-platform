"""Vendor-neutral payload models for the telephony provider protocol (E11-02).

These are the BBZ platform's own contract (MASTER_PROMPT §8.4/§8.12). A provider
translates its vendor events/results *into* these shapes; nothing here is a
Cisco/JTAPI/SIP detail. ``CallEvent`` mirrors
``packages/event-schemas/telephony_event.v1.json`` field-for-field.
"""

from __future__ import annotations

import datetime as _dt
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent


class LineState(StrEnum):
    IN_SERVICE = "in_service"
    OUT_OF_SERVICE = "out_of_service"
    UNKNOWN = "unknown"


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallLifecycleState(StrEnum):
    """Provider-observable call state. The core's own richer state (e.g.
    ``ended_pending_documentation``) is layered on top by the call aggregate."""

    OFFERED = "offered"
    RINGING = "ringing"
    CONNECTED = "connected"
    HELD = "held"
    TRANSFERRING = "transferring"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class LineInfo(_Frozen):
    line_id: str
    label: str | None = None
    state: LineState = LineState.UNKNOWN
    device_id: str | None = None


class PartyRef(_Frozen):
    number: str | None = None
    display_name: str | None = None


class CallSnapshot(_Frozen):
    #: the provider's call id (``source_call_id`` on the core side)
    call_id: str
    direction: CallDirection
    state: CallLifecycleState
    line_id: str | None = None
    calling: PartyRef | None = None
    called: PartyRef | None = None
    started_at: _dt.datetime | None = None


class CallEvent(_Frozen):
    """One normalized telephony event — the item type of
    :meth:`TelephonyProvider.subscribe_call_events`. Mirrors
    ``telephony_event.v1.json``."""

    telephony_event_id: str
    provider: str
    provider_cluster_id: str | None = None
    event_type: NormalizedTelephonyEvent
    raw_event_type: str
    source_call_id: str | None = None
    source_leg_id: str | None = None
    line_id: str | None = None
    device_id: str | None = None
    calling_number: str | None = None
    called_number: str | None = None
    redirecting_number: str | None = None
    display_name: str | None = None
    occurred_at: _dt.datetime
    received_at: _dt.datetime
    gateway_node: str
    correlation_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class CommandAccepted(_Frozen):
    """Acknowledgement that a control command was accepted by the provider. The
    resulting state change arrives asynchronously as a :class:`CallEvent`."""

    command_id: str
    accepted: bool = True
    #: the provider call id created (``dial``) or affected
    call_id: str | None = None
    detail: str | None = None


class CallerResolution(_Frozen):
    number: str
    matched: bool = False
    display_name: str | None = None
    contact_id: str | None = None
    #: vendor-neutral priority marker (e.g. ``blue`` / ``orange`` / ``red``);
    #: the core maps it to its own model
    priority: str | None = None


class ReconcileResult(_Frozen):
    """Full provider state, re-fetched after a failover / CONTROL_LEADER change
    (E11-14). The call aggregate reconciles its own state against this."""

    lines: list[LineInfo] = Field(default_factory=list)
    active_calls: list[CallSnapshot] = Field(default_factory=list)
    note: str | None = None


#: The capability names that belong to the telephony domain (§8.12). A telephony
#: provider advertises the subset it supports in its manifest.
TELEPHONY_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.CALL_ANSWER,
        Capability.CALL_DIAL,
        Capability.CALL_HANGUP,
        Capability.CALL_HOLD,
        Capability.CALL_RESUME,
        Capability.CALL_TRANSFER,
        Capability.CALL_CONFERENCE,
        Capability.CALL_SEND_DTMF,
        Capability.CALL_MONITORING,
        Capability.DEVICE_MONITORING,
        Capability.DIRECTORY_LOOKUP,
        Capability.MEDIA_TERMINATION,
    }
)
