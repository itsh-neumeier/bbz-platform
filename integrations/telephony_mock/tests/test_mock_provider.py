from __future__ import annotations

import pytest

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent
from bbz_integration_sdk.providers import TELEPHONY_METHODS, Provider, TelephonyProvider
from bbz_integration_sdk.providers.telephony_types import (
    CallEvent,
    CallLifecycleState,
    CommandAccepted,
    LineInfo,
)
from integrations.telephony_mock.adapter import MockTelephonyProvider, build


def test_satisfies_the_protocol_completely() -> None:
    m = MockTelephonyProvider()
    assert isinstance(m, TelephonyProvider)
    assert isinstance(m, Provider)
    for name in TELEPHONY_METHODS:
        assert callable(getattr(m, name))


async def test_capabilities_now_include_transfer_and_conference() -> None:
    caps = MockTelephonyProvider().capabilities()
    for c in (Capability.CALL_TRANSFER, Capability.CALL_CONFERENCE, Capability.CALL_SEND_DTMF):
        assert caps.has(c)


async def test_queries_return_typed_models() -> None:
    p = build({"lines": ["2001"]})
    await p.initialize()
    lines = await p.list_lines()
    assert lines and isinstance(lines[0], LineInfo)
    assert isinstance(await p.get_line_state("2001"), LineInfo)
    assert (await p.get_line_state("nope")).state.value == "unknown"
    assert await p.get_active_calls() == []


async def test_incoming_call_answer_hangup_lifecycle() -> None:
    p = MockTelephonyProvider(lines=["2001"])
    await p.initialize()

    cid = p.simulate_incoming(from_number="+49911500", to_line="2001", display_name="EVU")
    events = await p.drain_events()
    assert [e.event_type for e in events] == [
        NormalizedTelephonyEvent.CALL_OFFERED,
        NormalizedTelephonyEvent.CALL_RINGING,
    ]
    assert all(isinstance(e, CallEvent) for e in events)

    ack = await p.answer(call_id=cid, command_id="c1")
    assert isinstance(ack, CommandAccepted) and ack.call_id == cid
    (answered,) = await p.drain_events()
    assert answered.event_type is NormalizedTelephonyEvent.CALL_ANSWERED

    snaps = await p.get_active_calls()
    assert snaps[0].state is CallLifecycleState.CONNECTED and snaps[0].started_at is not None

    await p.hangup(call_id=cid, command_id="c2")
    (ended,) = await p.drain_events()
    assert ended.event_type is NormalizedTelephonyEvent.CALL_DISCONNECTED
    assert await p.get_active_calls() == []


async def test_multiple_waiting_calls() -> None:
    p = MockTelephonyProvider(lines=["2001", "2002"])
    a = p.simulate_incoming(from_number="111", to_line="2001")
    b = p.simulate_incoming(from_number="222", to_line="2002")
    await p.drain_events()
    active = {s.call_id for s in await p.get_active_calls()}
    assert active == {a, b}


async def test_commands_are_idempotent_on_command_id() -> None:
    p = MockTelephonyProvider(lines=["2001"])
    cid = p.simulate_incoming(from_number="1", to_line="2001")
    await p.drain_events()

    first = await p.answer(call_id=cid, command_id="same")
    (evt,) = await p.drain_events()  # first answer emits CALL_ANSWERED
    assert evt.event_type is NormalizedTelephonyEvent.CALL_ANSWERED
    second = await p.answer(call_id=cid, command_id="same")
    assert first == second
    assert await p.drain_events() == []  # the replay does nothing


async def test_transfer_requires_a_destination_and_emits_two_events() -> None:
    p = MockTelephonyProvider(lines=["2001"])
    cid = p.simulate_incoming(from_number="1", to_line="2001")
    await p.answer(call_id=cid, command_id="c0")
    await p.drain_events()

    with pytest.raises(ValueError, match="destination"):
        await p.transfer(call_id=cid, destination="", command_id="c1")

    await p.transfer(call_id=cid, destination="3000", command_id="c2")
    evs = [e.event_type for e in await p.drain_events()]
    assert evs == [
        NormalizedTelephonyEvent.CALL_TRANSFER_INITIATED,
        NormalizedTelephonyEvent.CALL_TRANSFERRED,
    ]


async def test_send_dtmf_never_leaks_the_code() -> None:
    p = MockTelephonyProvider(lines=["2001"])
    cid = p.simulate_incoming(from_number="1", to_line="2001")
    await p.answer(call_id=cid, command_id="c0")
    ack = await p.send_dtmf(call_id=cid, dtmf_profile_id="door-1", command_id="c1")
    assert "door-1" in (ack.detail or "")
    dump = ack.model_dump_json()
    assert "code" not in dump and "1234" not in dump


async def test_resolve_caller_known_and_unknown() -> None:
    p = MockTelephonyProvider(directory={"+49911500": "EVU Nord"})
    known = await p.resolve_caller(number="+49911500")
    assert known.matched and known.display_name == "EVU Nord"
    unknown = await p.resolve_caller(number="+490000")
    assert not unknown.matched and unknown.display_name is None


async def test_provider_out_of_service_then_in_service() -> None:
    p = MockTelephonyProvider()
    await p.initialize()
    p.simulate_provider_out_of_service()
    p.simulate_provider_in_service()
    evs = [e.event_type for e in await p.drain_events()]
    assert evs == [
        NormalizedTelephonyEvent.CTI_PROVIDER_OUT_OF_SERVICE,
        NormalizedTelephonyEvent.CTI_PROVIDER_IN_SERVICE,
    ]
    assert (await p.health()).state.value == "healthy"


async def test_reconnect_replay_re_delivers_the_backlog() -> None:
    p = MockTelephonyProvider(lines=["2001"])
    p.simulate_incoming(from_number="1", to_line="2001")
    first = await p.drain_events()
    assert len(first) == 2

    p.replay_backlog()
    replayed = await p.drain_events()
    assert [e.telephony_event_id for e in replayed] == [e.telephony_event_id for e in first]


async def test_reconcile_reports_lines_and_active_calls() -> None:
    p = MockTelephonyProvider(lines=["2001"])
    p.simulate_incoming(from_number="1", to_line="2001")
    await p.drain_events()
    result = await p.reconcile()
    assert [line.line_id for line in result.lines] == ["2001"]
    assert len(result.active_calls) == 1
