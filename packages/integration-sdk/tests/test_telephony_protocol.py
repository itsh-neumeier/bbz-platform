"""The telephony provider protocol is complete, typed and mock-satisfiable (E11-02)."""

from __future__ import annotations

import datetime as _dt
import inspect

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent
from bbz_integration_sdk.providers import (
    TELEPHONY_CAPABILITIES,
    TELEPHONY_METHODS,
    Provider,
    TelephonyProvider,
)
from bbz_integration_sdk.providers.telephony_types import (
    CallDirection,
    CallEvent,
    CallLifecycleState,
    CallSnapshot,
    CommandAccepted,
    LineInfo,
    LineState,
)

# every §8.12 control/query method (lifecycle lives on Provider)
_SECTION_8_12 = {
    "list_lines",
    "get_line_state",
    "get_active_calls",
    "subscribe_call_events",
    "dial",
    "answer",
    "hangup",
    "hold",
    "resume",
    "transfer",
    "conference",
    "send_dtmf",
    "resolve_caller",
    "reconcile",
}


def test_protocol_declares_exactly_the_section_8_12_methods() -> None:
    declared = {
        n
        for n, _ in inspect.getmembers(TelephonyProvider, predicate=callable)
        if not n.startswith("_")
    }
    telephony_only = declared - {
        n for n, _ in inspect.getmembers(Provider, predicate=callable) if not n.startswith("_")
    }
    assert telephony_only == _SECTION_8_12 == TELEPHONY_METHODS


def test_every_method_is_fully_annotated() -> None:
    for name in TELEPHONY_METHODS:
        sig = inspect.signature(getattr(TelephonyProvider, name))
        assert sig.return_annotation is not inspect.Signature.empty, name
        for p in sig.parameters.values():
            if p.name == "self":
                continue
            assert p.annotation is not inspect.Parameter.empty, f"{name}.{p.name}"


def test_telephony_capabilities_cover_the_domain() -> None:
    telephony_caps = {
        c for c in Capability if c.value.startswith(("call.", "device.", "directory.", "media."))
    }
    assert telephony_caps == TELEPHONY_CAPABILITIES


def test_call_event_mirrors_the_telephony_event_schema() -> None:
    # the field set must match packages/event-schemas/telephony_event.v1.json
    expected = {
        "telephony_event_id",
        "provider",
        "provider_cluster_id",
        "event_type",
        "raw_event_type",
        "source_call_id",
        "source_leg_id",
        "line_id",
        "device_id",
        "calling_number",
        "called_number",
        "redirecting_number",
        "display_name",
        "occurred_at",
        "received_at",
        "gateway_node",
        "correlation_id",
        "metadata",
    }
    assert set(CallEvent.model_fields) == expected


def test_payload_models_round_trip() -> None:
    now = _dt.datetime.now(_dt.UTC)
    ev = CallEvent(
        telephony_event_id="t1",
        provider="telephony_mock",
        event_type=NormalizedTelephonyEvent.CALL_RINGING,
        raw_event_type="MockRing",
        source_call_id="c-1",
        occurred_at=now,
        received_at=now,
        gateway_node="BBZ-SRV01",
    )
    assert CallEvent.model_validate_json(ev.model_dump_json()) == ev

    snap = CallSnapshot(
        call_id="c-1", direction=CallDirection.INBOUND, state=CallLifecycleState.RINGING
    )
    assert snap.state is CallLifecycleState.RINGING
    assert LineInfo(line_id="1001").state is LineState.UNKNOWN
    assert CommandAccepted(command_id="x").accepted is True


def test_the_mock_structurally_satisfies_the_protocol() -> None:
    from integrations.telephony_mock.adapter import MockTelephonyProvider

    m = MockTelephonyProvider()
    assert isinstance(m, TelephonyProvider)
    assert isinstance(m, Provider)
    for name in TELEPHONY_METHODS:
        assert callable(getattr(m, name)), name
