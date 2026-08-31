"""Normalized inbound signal (roadmap E15-04; ``.ai/TECHNICAL_TRIGGERS.md``).

Every integration edge (telephony, video alarm, door, BMA, panic) turns its
provider event into this one provider-neutral shape **before** any trigger-rule
evaluation. The core never inspects a raw Cisco/Coda/Siedle payload — only the
allowlisted fields in ``inbound_signal.v1.json`` exist.

Pure: schema validation + the telephony→signal mapper. Persisting a signal
through the E04-07 inbox is :mod:`bbz_core.infra.inbound_signals`; wiring the
engine onto it is E15-09.
"""

from __future__ import annotations

import enum
from functools import lru_cache
from typing import Any

import jsonschema

from bbz_event_schemas import inbound_signal_schema


class InboundSignalType(enum.StrEnum):
    CALL_RINGING = "CALL_RINGING"
    CALL_ANSWERED = "CALL_ANSWERED"
    CALL_ENDED = "CALL_ENDED"
    TECHNICAL_ALARM_RAISED = "TECHNICAL_ALARM_RAISED"
    PANIC_ALARM_RAISED = "PANIC_ALARM_RAISED"
    DOORBELL_RINGING = "DOORBELL_RINGING"
    BMA_ALARM_CALL = "BMA_ALARM_CALL"


class InboundSignalRejected(ValueError):
    """A signal does not validate against ``inbound_signal.v1.json``."""


#: telephony ``event_type`` → the rule-relevant inbound signal it maps to.
#: Line / device / CTI events are not signals and return ``None``.
_FROM_TELEPHONY: dict[str, InboundSignalType] = {
    "CALL_OFFERED": InboundSignalType.CALL_RINGING,
    "CALL_RINGING": InboundSignalType.CALL_RINGING,
    "CALL_ANSWERED": InboundSignalType.CALL_ANSWERED,
    "CALL_CONNECTED": InboundSignalType.CALL_ANSWERED,
    "CALL_DISCONNECTED": InboundSignalType.CALL_ENDED,
    "CALL_FAILED": InboundSignalType.CALL_ENDED,
}


@lru_cache
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        inbound_signal_schema(), format_checker=jsonschema.FormatChecker()
    )


def validate_inbound_signal(signal: dict[str, Any]) -> None:
    errors = sorted(_validator().iter_errors(signal), key=str)
    if errors:
        raise InboundSignalRejected("; ".join(e.message for e in errors))


def from_telephony_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Map a ``telephony_event.v1`` dict to an ``inbound_signal.v1`` dict, or
    ``None`` when the telephony event is not a rule-relevant signal.

    Only allowlisted fields are copied — a vendor field in ``event`` is dropped,
    never carried forward. The gateway may pre-fill ``metadata.cti_route_point``
    / ``metadata.technical_endpoint_id`` / ``metadata.direction``; otherwise the
    engine resolves the endpoint (E15-05).
    """
    signal_type = _FROM_TELEPHONY.get(str(event.get("event_type", "")))
    if signal_type is None:
        return None

    meta = event.get("metadata") or {}
    direction = meta.get("direction") if meta.get("direction") in ("inbound", "outbound") else None
    signal: dict[str, Any] = {
        "signal_type": signal_type.value,
        "provider": event["provider"],
        "occurred_at": event["occurred_at"],
        "received_at": event["received_at"],
        "gateway_node": event["gateway_node"],
        "correlation_id": event.get("correlation_id"),
        "source": {
            "ani": event.get("calling_number"),
            "dnis": event.get("called_number"),
            "source_call_id": event.get("source_call_id"),
            "cti_route_point": meta.get("cti_route_point"),
            "technical_endpoint_id": meta.get("technical_endpoint_id"),
            "direction": direction,
        },
    }
    validate_inbound_signal(signal)
    return signal


#: BBZ severity words the inbound signal's ``source.severity`` enum accepts
_SIGNAL_SEVERITIES = frozenset({"critical", "high", "medium", "low"})


def from_incoming_alarm(alarm_event: dict[str, Any]) -> dict[str, Any]:
    """Map a normalized ``provider_alarm_event.v1`` dict (E16-04) to an
    ``inbound_signal.v1`` dict for the trigger engine (E16-07).

    A ``panic_button`` subtype becomes ``PANIC_ALARM_RAISED``; every other alarm
    becomes ``TECHNICAL_ALARM_RAISED``. Only allowlisted, rule-relevant fields
    cross over — the raw provider payload is already gone by this point (E16-04).
    ``severity_external`` is carried only when it is already one of the BBZ
    severity words; the BBZ priority itself is decided by the matched rule /
    admin config (E16-06), not here.
    """
    subtype = alarm_event.get("alarm_subtype")
    signal_type = (
        InboundSignalType.PANIC_ALARM_RAISED
        if subtype == "panic_button"
        else InboundSignalType.TECHNICAL_ALARM_RAISED
    )
    severity = str(alarm_event.get("severity_external") or "").lower()
    signal: dict[str, Any] = {
        "signal_type": signal_type.value,
        "provider": alarm_event["provider"],
        "occurred_at": alarm_event.get("occurred_at") or alarm_event["received_at"],
        "received_at": alarm_event["received_at"],
        "gateway_node": alarm_event["provider_instance_id"],
        "correlation_id": None,
        "source": {
            "external_source_id": alarm_event.get("source_external_id"),
            "site": alarm_event.get("site_external_id"),
            "alarm_subtype": subtype,
            "severity": severity if severity in _SIGNAL_SEVERITIES else None,
        },
    }
    validate_inbound_signal(signal)
    return signal
