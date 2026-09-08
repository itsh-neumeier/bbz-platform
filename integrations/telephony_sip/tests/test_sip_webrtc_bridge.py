"""Operator media bridge over ARI (E13-11 / #816, ADR-0035): ``answer`` /
``dial`` with an ``operator_key`` put the operator's WebRTC endpoint into a
mixing bridge with the trunk channel; the pump joins the operator leg on its
StasisStart and never surfaces it as a call; the bridge is torn down with the
call."""

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


def _handler(calls: list[str], *, op_channel_id: str = "op-ch-1") -> Any:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        path, method = request.url.path, request.method
        if path == "/ari/bridges" and method == "POST":
            return httpx.Response(200, json={"id": "br-1"})
        if path == "/ari/channels" and method == "POST":
            return httpx.Response(200, json={"id": op_channel_id})
        return httpx.Response(204)

    return handler


async def _answered_provider(calls: list[str]) -> SipTelephonyProvider:
    p = SipTelephonyProvider(ari=_client(_handler(calls)), line_endpoints={"l": "PJSIP/l"})
    p._channels["call@pbx"] = "trunk-ch-1"  # the pump has seen the inbound trunk call
    return p


async def test_answer_with_an_operator_key_bridges_the_trunk_and_operator_legs() -> None:
    calls: list[str] = []
    p = await _answered_provider(calls)

    ack = await p.answer(call_id="call@pbx", command_id="a1", operator_key="op-abc")
    assert ack.accepted

    assert "POST /ari/channels/trunk-ch-1/answer?" in calls
    assert "POST /ari/bridges?type=mixing" in calls
    assert any("/ari/bridges/br-1/addChannel?channel=trunk-ch-1" in c for c in calls)
    orig = next(c for c in calls if c.startswith("POST /ari/channels?"))
    assert "endpoint=PJSIP%2Fop-abc" in orig and "app=bbz-sip" in orig

    assert "op-ch-1" in p._operator_channels
    assert p._pending_operator_bridge == {"op-ch-1": "br-1"}
    assert p._call_bridges == {"call@pbx": "br-1"}
    await p.shutdown()


async def test_answer_without_an_operator_key_is_unchanged() -> None:
    calls: list[str] = []
    p = await _answered_provider(calls)
    ack = await p.answer(call_id="call@pbx", command_id="a1")
    assert ack.accepted
    assert not any("bridge" in c for c in calls)
    assert not p._call_bridges
    await p.shutdown()


async def test_answer_is_idempotent_and_does_not_bridge_twice() -> None:
    calls: list[str] = []
    p = await _answered_provider(calls)
    await p.answer(call_id="call@pbx", command_id="same", operator_key="op-abc")
    n = len(calls)
    await p.answer(call_id="call@pbx", command_id="same", operator_key="op-abc")
    assert len(calls) == n  # replayed from the idempotency cache
    await p.shutdown()


async def test_a_failed_operator_originate_still_reports_the_call_answered() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ari/bridges" and request.method == "POST":
            return httpx.Response(200, json={"id": "br-1"})
        if request.url.path == "/ari/channels" and request.method == "POST":
            return httpx.Response(503)  # the operator endpoint is not registered
        return httpx.Response(204)

    p = SipTelephonyProvider(ari=_client(handler))
    p._channels["call@pbx"] = "trunk-ch-1"
    ack = await p.answer(call_id="call@pbx", command_id="a1", operator_key="op-down")
    assert ack.accepted is True
    assert "operator bridge failed" in (ack.detail or "")
    await p.shutdown()


# --- pump: join the operator leg on StasisStart, hide it, tear down on end ----


class _FakeAri:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events
        self.ws = type("W", (), {"connected": True})()
        self.app_name = "bbz-sip"
        self.bridged: list[tuple[str, str]] = []
        self.destroyed: list[str] = []
        self.created_bridges = 0
        self.originated: list[str] = []
        self.closed = False

    async def events(self, *, reconnect: bool = True) -> Any:
        for e in self._events:
            yield e
        await asyncio.Event().wait()

    async def list_channels(self) -> list[dict[str, Any]]:
        return []

    async def create_bridge(self) -> str:
        self.created_bridges += 1
        return f"br-{self.created_bridges}"

    async def add_to_bridge(self, bridge_id: str, channel_id: str) -> None:
        self.bridged.append((bridge_id, channel_id))

    async def destroy_bridge(self, bridge_id: str) -> None:
        self.destroyed.append(bridge_id)

    async def originate(self, *, endpoint: str, app: str = "", caller_id: str = "BBZ") -> Any:
        self.originated.append(endpoint)
        return {"id": "op-ch-9"}

    async def aclose(self) -> None:
        self.closed = True


async def _drain_until(p: SipTelephonyProvider, n: int) -> None:
    for _ in range(300):
        await asyncio.sleep(0)
        if p._buffer.qsize() >= n:
            return


async def test_pump_joins_the_operator_leg_hides_it_and_tears_the_bridge_down() -> None:
    op_ch = {"id": "op-ch-9", "name": "PJSIP/op-abc-2"}
    trunk = {"id": "t-1", "channelvars": {"SIPCALLID": "call@pbx"}}
    ari = _FakeAri(
        [
            {"type": "StasisStart", "args": ["op-ch-9"], "channel": op_ch},
            {"type": "StasisEnd", "channel": trunk},
        ]
    )
    p = SipTelephonyProvider(ari=ari)  # type: ignore[arg-type]
    p._channels["call@pbx"] = "t-1"
    p._operator_channels.add("op-ch-9")
    p._pending_operator_bridge["op-ch-9"] = "br-7"
    p._call_bridges["call@pbx"] = "br-7"
    p._call_operator_ch["call@pbx"] = "op-ch-9"

    await p.initialize()
    await _drain_until(p, 1)

    assert ("br-7", "op-ch-9") in ari.bridged  # joined on its StasisStart
    drained = await p.drain_events()
    assert [e.event_type.value for e in drained] == ["CALL_DISCONNECTED"]  # only the trunk leg
    assert p._operator_channels == set()
    assert ari.destroyed == ["br-7"]
    await p.shutdown()


async def test_dial_with_an_operator_key_bridges_once_the_far_end_answers() -> None:
    trunk_up = {"id": "out-1", "state": "Up"}
    ari = _FakeAri([{"type": "ChannelStateChange", "channel": trunk_up}])
    p = SipTelephonyProvider(ari=ari)  # type: ignore[arg-type]
    # dial() has run and is waiting for the answer:
    p._channels["out-1"] = "out-1"
    p._dial_operator["out-1"] = "op-abc"

    await p.initialize()
    await _drain_until(p, 1)

    assert ari.created_bridges == 1
    assert ("br-1", "out-1") in ari.bridged  # the trunk leg joined
    assert ari.originated == ["PJSIP/op-abc"]  # the operator leg originated
    assert "out-1" not in p._dial_operator  # consumed
    await p.shutdown()
