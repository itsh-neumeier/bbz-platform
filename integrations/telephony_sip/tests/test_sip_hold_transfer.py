"""Hold / transfer over the trunk + queue music (E13-13 / #819).

- blind transfer routes ``PJSIP/<dest>@<trunk>`` for a trunk-backed line (the
  same fix ``dial`` needed in E13-10), plain ``PJSIP/<dest>`` otherwise;
- ``hold`` on a bridged call with a hold-MoH class streams the music to the
  caller's leg (ARI ``channels/{id}/moh``) instead of a bare SIP hold;
- an inbound caller waiting for an operator hears the line's ``ring`` MoH class;
  BBZ answers the channel to stream it, so that CALL_ANSWERED is swallowed until
  a real pickup.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from integrations.telephony_sip.adapter import SipTelephonyProvider
from integrations.telephony_sip.ari import AriClient, AriConfig


def _client(handler: Any) -> AriClient:
    return AriClient(
        AriConfig(host="pbx.test", username="bbz", password="s3cret"),
        transport=httpx.MockTransport(handler),
    )


def _rec(calls: list[str]) -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        return httpx.Response(204)

    return handler


# --- transfer over the trunk ------------------------------------------------


async def test_transfer_routes_through_the_call_s_trunk() -> None:
    calls: list[str] = []
    p = SipTelephonyProvider(
        ari=_client(_rec(calls)),
        line_endpoints={"leonet-8870": "PJSIP/{dest}@leonet-01"},
    )
    p._channels["c@pbx"] = "ch-1"
    p._call_lines["c@pbx"] = "leonet-8870"

    ack = await p.transfer(call_id="c@pbx", destination="017012345678", command_id="t1")
    assert ack.accepted and ack.detail == "blind transfer"
    redirect = next(c for c in calls if "/redirect" in c)
    assert "endpoint=PJSIP%2F017012345678%40leonet-01" in redirect
    await p.shutdown()


async def test_transfer_without_a_trunk_line_uses_the_plain_endpoint() -> None:
    calls: list[str] = []
    p = SipTelephonyProvider(ari=_client(_rec(calls)))
    p._channels["c@pbx"] = "ch-1"  # no _call_lines entry

    ack = await p.transfer(call_id="c@pbx", destination="1001", command_id="t1")
    assert ack.accepted
    assert any("redirect?endpoint=PJSIP%2F1001" in c for c in calls)
    await p.shutdown()


# --- hold / resume with the line's hold-MoH class --------------------------


async def _bridged(calls: list[str]) -> SipTelephonyProvider:
    p = SipTelephonyProvider(
        ari=_client(_rec(calls)),
        line_moh={"leonet-8870": {"hold": "bbz-moh-abc", "ring": "bbz-moh-xyz"}},
    )
    p._channels["c@pbx"] = "trunk-ch"
    p._call_lines["c@pbx"] = "leonet-8870"
    p._call_bridges["c@pbx"] = "br-1"  # an operator is on the call (E13-11)
    return p


async def test_hold_on_a_bridged_call_streams_the_line_moh_then_resume_stops_it() -> None:
    calls: list[str] = []
    p = await _bridged(calls)

    h = await p.hold(call_id="c@pbx", command_id="h1")
    assert h.accepted and h.detail == "hold"
    assert "POST /ari/channels/trunk-ch/moh?mohClass=bbz-moh-abc" in calls
    assert "c@pbx" in p._held_via_moh
    # the pump gets a synthetic CALL_HELD (ARI moh emits no ChannelHold)
    assert (await p.drain_events())[0].event_type.value == "CALL_HELD"

    r = await p.resume(call_id="c@pbx", command_id="r1")
    assert r.accepted and r.detail == "resume"
    assert "DELETE /ari/channels/trunk-ch/moh?" in calls
    assert "c@pbx" not in p._held_via_moh
    assert (await p.drain_events())[0].event_type.value == "CALL_RESUMED"
    await p.shutdown()


async def test_hold_without_a_bridge_or_moh_class_is_a_plain_sip_hold() -> None:
    calls: list[str] = []
    p = SipTelephonyProvider(ari=_client(_rec(calls)))  # no line_moh, no bridge
    p._channels["c@pbx"] = "ch-1"

    ack = await p.hold(call_id="c@pbx", command_id="h1")
    assert ack.accepted
    assert "POST /ari/channels/ch-1/hold?" in calls
    assert not any("/moh" in c for c in calls)

    assert (await p.resume(call_id="c@pbx", command_id="r1")).accepted
    assert any("DELETE /ari/channels/ch-1/hold?" in c for c in calls)
    await p.shutdown()


# --- queue music while a caller waits for an operator ---------------------


class _FakeAri:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events
        self.ws = type("W", (), {"connected": True})()
        self.app_name = "bbz-sip"
        self.moh_started: list[tuple[str, str]] = []
        self.moh_stopped: list[str] = []
        self.answered: list[str] = []
        self.closed = False

    async def events(self, *, reconnect: bool = True) -> Any:
        for e in self._events:
            yield e
        await asyncio.Event().wait()

    async def list_channels(self) -> list[dict[str, Any]]:
        return []

    async def start_moh(self, channel_id: str, moh_class: str = "") -> None:
        self.moh_started.append((channel_id, moh_class))

    async def stop_moh(self, channel_id: str) -> None:
        self.moh_stopped.append(channel_id)

    async def answer(self, channel_id: str) -> None:
        self.answered.append(channel_id)

    async def aclose(self) -> None:
        self.closed = True


def _chan(**kw: Any) -> dict[str, Any]:
    base = {"id": "ari-7", "name": "PJSIP/leonet-01-1", "channelvars": {"SIPCALLID": "in@pbx"}}
    base.update(kw)
    return base


async def _drain_until(p: SipTelephonyProvider, n: int) -> None:
    for _ in range(300):
        await asyncio.sleep(0)
        if p._buffer.qsize() >= n:
            return


async def test_ring_moh_starts_on_an_inbound_call_and_the_auto_answer_is_hidden() -> None:
    ari = _FakeAri(
        [
            {"type": "StasisStart", "args": ["leonet-8870"], "channel": _chan()},
            {"type": "ChannelStateChange", "channel": _chan(state="Up")},  # the moh auto-answer
        ]
    )
    p = SipTelephonyProvider(ari=ari, line_moh={"leonet-8870": {"ring": "bbz-moh-wait"}})  # type: ignore[arg-type]
    await p.initialize()
    await _drain_until(p, 1)

    assert ari.moh_started == [("ari-7", "bbz-moh-wait")]
    assert "in@pbx" in p._ring_moh
    drained = await p.drain_events()
    kinds = [e.event_type.value for e in drained]
    assert "CALL_RINGING" in kinds
    assert "CALL_ANSWERED" not in kinds  # swallowed — no operator yet
    await p.shutdown()


async def test_operator_answer_stops_ring_moh_and_emits_the_real_answered() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        return httpx.Response(204)

    p = SipTelephonyProvider(
        ari=_client(handler), line_moh={"leonet-8870": {"ring": "bbz-moh-wait"}}
    )
    p._channels["in@pbx"] = "ari-7"
    p._call_lines["in@pbx"] = "leonet-8870"
    p._ring_moh.add("in@pbx")  # the pump started ring MoH earlier

    ack = await p.answer(call_id="in@pbx", command_id="a1")
    assert ack.accepted
    assert "DELETE /ari/channels/ari-7/moh" in calls
    assert "POST /ari/channels/ari-7/answer" in calls
    assert "in@pbx" not in p._ring_moh
    assert (await p.drain_events())[-1].event_type.value == "CALL_ANSWERED"  # synthesized
    await p.shutdown()
