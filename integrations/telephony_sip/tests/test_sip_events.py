"""ARI event → normalized CallEvent mapping (E13-04) + the adapter's event
buffer / ``drain_events`` pump path."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from integrations.telephony_sip.adapter import SipTelephonyProvider, build
from integrations.telephony_sip.events import map_ari_event

_GW = {"provider": "telephony_sip", "gateway_node": "sip-lab"}


def _channel(**kw: Any) -> dict[str, Any]:
    base = {
        "id": "1700000000.1",
        "name": "PJSIP/line1-00000001",
        "state": "Ring",
        "caller": {"name": "Leitwarte", "number": "+4991150099"},
        "connected": {"number": "2001"},
        "dialplan": {"context": "bbz-sip", "exten": "2001"},
        "channelvars": {"SIPCALLID": "a1b2c3@pbx"},
    }
    base.update(kw)
    return base


def test_stasis_start_is_call_ringing_inbound_with_the_sip_call_id() -> None:
    ev = map_ari_event({"type": "StasisStart", "channel": _channel()}, **_GW)
    assert ev is not None
    assert ev.event_type.value == "CALL_RINGING"
    assert ev.source_call_id == "a1b2c3@pbx"  # the SIP Call-ID, not the ARI channel id
    assert ev.calling_number == "+4991150099"
    assert ev.called_number == "2001"
    assert ev.display_name == "Leitwarte"
    assert ev.metadata["direction"] == "inbound"
    assert ev.metadata["channel_id"] == "1700000000.1"
    assert ev.provider == "telephony_sip" and ev.gateway_node == "sip-lab"


def test_falls_back_to_the_channel_id_when_no_sip_call_id_var() -> None:
    ch = _channel(channelvars={})
    ev = map_ari_event({"type": "StasisStart", "channel": ch}, **_GW)
    assert ev is not None and ev.source_call_id == "1700000000.1"


def _sc(state: str) -> dict[str, Any]:
    return {"type": "ChannelStateChange", "channel": {"id": "c", "state": state}}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_sc("Up"), "CALL_ANSWERED"),
        (_sc("Ringing"), "CALL_RINGING"),
        ({"type": "ChannelHold", "channel": {"id": "c"}}, "CALL_HELD"),
        ({"type": "ChannelUnhold", "channel": {"id": "c"}}, "CALL_RESUMED"),
        ({"type": "StasisEnd", "channel": {"id": "c"}}, "CALL_DISCONNECTED"),
        ({"type": "ChannelHangupRequest", "channel": {"id": "c"}}, "CALL_DISCONNECTED"),
        ({"type": "ChannelDestroyed", "channel": {"id": "c"}}, "CALL_DISCONNECTED"),
    ],
)
def test_lifecycle_events_map_to_the_normalized_enum(raw: dict[str, Any], expected: str) -> None:
    ev = map_ari_event(raw, **_GW)
    assert ev is not None and ev.event_type.value == expected


def _peer(status: str) -> dict[str, Any]:
    return {"type": "PeerStatusChange", "peer": {"peer_id": "PJSIP/line1", "peer_status": status}}


def test_peer_status_change_maps_device_registration() -> None:
    reg = map_ari_event(_peer("Reachable"), **_GW)
    assert reg is not None and reg.event_type.value == "DEVICE_REGISTERED"
    assert reg.device_id == "PJSIP/line1"
    unreg = map_ari_event(_peer("Unreachable"), **_GW)
    assert unreg is not None and unreg.event_type.value == "DEVICE_UNREGISTERED"


def test_unremarkable_events_are_dropped() -> None:
    for kind in ("ChannelVarset", "PlaybackStarted", "RecordingFinished", "Dial"):
        assert map_ari_event({"type": kind, "channel": {"id": "c"}}, **_GW) is None
    assert map_ari_event(_sc("Down"), **_GW) is None  # a state change we don't surface


# --- adapter buffer / drain -------------------------------------------------


class _FakeAri:
    """Feeds a fixed list of raw ARI events, then blocks (like a live WS)."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events
        self.ws = type("W", (), {"connected": True})()
        self.closed = False

    async def events(self, *, reconnect: bool = True) -> Any:
        for e in self._events:
            yield e
        await asyncio.Event().wait()  # stay open

    async def list_channels(self) -> list[dict[str, Any]]:
        return []

    async def aclose(self) -> None:
        self.closed = True


async def test_pump_buffers_mapped_events_and_drain_pops_them() -> None:
    ari = _FakeAri(
        [
            {"type": "StasisStart", "channel": _channel()},
            {"type": "ChannelVarset", "channel": {"id": "x"}},  # dropped
            {"type": "ChannelStateChange", "channel": _channel(state="Up")},
            {"type": "StasisEnd", "channel": _channel()},
        ]
    )
    p = SipTelephonyProvider(ari=ari)  # type: ignore[arg-type]
    await p.initialize()
    for _ in range(50):  # let the pump task run
        await asyncio.sleep(0)
        if p._buffer.qsize() >= 3:
            break

    drained = await p.drain_events()
    assert [e.event_type.value for e in drained] == [
        "CALL_RINGING",
        "CALL_ANSWERED",
        "CALL_DISCONNECTED",
    ]
    assert await p.drain_events() == []  # buffer emptied
    await p.shutdown()
    assert ari.closed is True


async def test_build_without_a_gateway_has_no_pump_and_drains_nothing() -> None:
    p = build({"lines": ["2001"]})
    await p.initialize()
    assert p._pump_task is None
    assert await p.drain_events() == []
    await p.shutdown()
