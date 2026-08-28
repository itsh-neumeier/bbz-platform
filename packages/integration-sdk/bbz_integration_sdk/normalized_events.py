"""BBZ-defined, vendor-neutral normalized signal/event names.

These names are the platform's own contract. Vendor payloads (Cisco JTAPI, Coda,
Siedle, ...) are translated *into* these by the respective integration before the
core ever sees them (MASTER_PROMPT §8.4, TECHNICAL_TRIGGERS.md). Nothing here is
a vendor API detail.
"""

from __future__ import annotations

from enum import StrEnum


class NormalizedTelephonyEvent(StrEnum):
    CALL_OFFERED = "CALL_OFFERED"
    CALL_RINGING = "CALL_RINGING"
    CALL_ANSWERED = "CALL_ANSWERED"
    CALL_CONNECTED = "CALL_CONNECTED"
    CALL_HELD = "CALL_HELD"
    CALL_RESUMED = "CALL_RESUMED"
    CALL_TRANSFER_INITIATED = "CALL_TRANSFER_INITIATED"
    CALL_TRANSFERRED = "CALL_TRANSFERRED"
    CALL_CONFERENCED = "CALL_CONFERENCED"
    CALL_DISCONNECTED = "CALL_DISCONNECTED"
    CALL_FAILED = "CALL_FAILED"
    LINE_IN_SERVICE = "LINE_IN_SERVICE"
    LINE_OUT_OF_SERVICE = "LINE_OUT_OF_SERVICE"
    DEVICE_REGISTERED = "DEVICE_REGISTERED"
    DEVICE_UNREGISTERED = "DEVICE_UNREGISTERED"
    CTI_PROVIDER_IN_SERVICE = "CTI_PROVIDER_IN_SERVICE"
    CTI_PROVIDER_OUT_OF_SERVICE = "CTI_PROVIDER_OUT_OF_SERVICE"


class NormalizedInboundSignal(StrEnum):
    """Provider-neutral inbound signals for the trigger engine (ADR-0004)."""

    CALL_RINGING = "CALL_RINGING"
    DOORBELL_RINGING = "DOORBELL_RINGING"
    BMA_ALARM_CALL = "BMA_ALARM_CALL"
    PANIC_ALARM_RAISED = "PANIC_ALARM_RAISED"
    TECHNICAL_ALARM_RAISED = "TECHNICAL_ALARM_RAISED"
