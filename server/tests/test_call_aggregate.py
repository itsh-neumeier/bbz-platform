"""The pure call aggregate — transition matrix + chaotic provider sequences (E11-04)."""

from __future__ import annotations

import pytest

from bbz_core.domain.telephony import CallAggregate, CallDirection, CallState
from bbz_core.domain.telephony.state import business_event_for, provider_target_state
from bbz_core.infra.models import telephony as _model


def _agg(state: CallState = CallState.OFFERED) -> CallAggregate:
    a = CallAggregate.start(
        bbz_call_id="CALL-1", direction=CallDirection.INBOUND, source_call_id="s1"
    )
    a.state = state
    return a


def test_domain_and_model_state_values_match() -> None:
    assert {s.value for s in CallState} == {s.value for s in _model.CallState}
    assert {d.value for d in CallDirection} == {d.value for d in _model.CallDirection}


def test_happy_path_emits_ringing_answered_ended() -> None:
    a = _agg()
    a.apply_provider_event("CALL_RINGING")
    a.apply_provider_event("CALL_ANSWERED")
    a.apply_provider_event("CALL_DISCONNECTED")
    assert a.state is CallState.DISCONNECTED
    assert [e.type for e in a.collect_events()] == ["CALL_RINGING", "CALL_ANSWERED", "CALL_ENDED"]


def test_offered_then_answered_still_emits_answered_once() -> None:
    a = _agg()
    a.apply_provider_event("CALL_OFFERED")  # offered -> offered, nothing
    a.apply_provider_event("CALL_ANSWERED")  # offered -> connected
    a.apply_provider_event("CALL_CONNECTED")  # connected -> connected, nothing
    assert [e.type for e in a.collect_events()] == ["CALL_ANSWERED"]


def test_hold_and_resume_do_not_re_emit_answered() -> None:
    a = _agg(CallState.CONNECTED)
    a.apply_provider_event("CALL_HELD")
    a.apply_provider_event("CALL_RESUMED")
    a.apply_provider_event("CALL_HELD")
    assert a.state is CallState.HELD
    assert a.collect_events() == []  # held/resumed carry no business event


def test_failure_emits_call_ended() -> None:
    a = _agg(CallState.RINGING)
    a.apply_provider_event("CALL_FAILED")
    assert a.state is CallState.FAILED
    assert [e.type for e in a.collect_events()] == ["CALL_ENDED"]


def test_events_after_a_terminal_state_are_absorbed() -> None:
    a = _agg(CallState.DISCONNECTED)
    for et in ("CALL_RINGING", "CALL_ANSWERED", "CALL_HELD", "CALL_DISCONNECTED"):
        a.apply_provider_event(et)
    assert a.state is CallState.DISCONNECTED
    assert a.collect_events() == []


def test_unknown_and_non_call_events_are_ignored() -> None:
    a = _agg(CallState.CONNECTED)
    for et in (
        "LINE_OUT_OF_SERVICE",
        "CTI_PROVIDER_OUT_OF_SERVICE",
        "DEVICE_REGISTERED",
        "NONSENSE",
    ):
        a.apply_provider_event(et)
    assert a.state is CallState.CONNECTED
    assert a.collect_events() == []


@pytest.mark.parametrize(
    "sequence",
    [
        # provider replays a truncated backlog, out of order
        ["CALL_ANSWERED", "CALL_RINGING", "CALL_DISCONNECTED", "CALL_ANSWERED"],
        ["CALL_DISCONNECTED", "CALL_RINGING"],
        ["CALL_HELD", "CALL_HELD", "CALL_RESUMED", "CALL_FAILED", "CALL_ANSWERED"],
        ["CALL_TRANSFER_INITIATED", "CALL_TRANSFERRED", "CALL_DISCONNECTED"],
    ],
)
def test_chaotic_sequences_never_crash_and_end_terminal_or_stable(sequence: list[str]) -> None:
    a = _agg()
    for et in sequence:
        a.apply_provider_event(et)  # must not raise
    assert isinstance(a.state, CallState)
    ends = [e.type for e in a.collect_events()]
    # a business "ended" event fires at most once
    assert ends.count("CALL_ENDED") <= 1


def test_business_event_helper_first_connect_only() -> None:
    assert business_event_for(CallState.OFFERED, CallState.RINGING) == "CALL_RINGING"
    assert business_event_for(CallState.RINGING, CallState.CONNECTED) == "CALL_ANSWERED"
    assert business_event_for(CallState.HELD, CallState.CONNECTED) is None
    assert business_event_for(CallState.CONNECTED, CallState.DISCONNECTED) == "CALL_ENDED"
    assert business_event_for(CallState.DISCONNECTED, CallState.FAILED) is None


def test_provider_target_state_covers_every_call_event() -> None:
    for et in (
        "CALL_OFFERED",
        "CALL_RINGING",
        "CALL_ANSWERED",
        "CALL_CONNECTED",
        "CALL_HELD",
        "CALL_RESUMED",
        "CALL_TRANSFER_INITIATED",
        "CALL_TRANSFERRED",
        "CALL_CONFERENCED",
        "CALL_DISCONNECTED",
        "CALL_FAILED",
    ):
        assert provider_target_state(et) is not None
    assert provider_target_state("LINE_IN_SERVICE") is None
