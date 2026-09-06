"""SIP call control over ARI (E13-05): the TelephonyProvider verbs drive the
gateway, resolve the SIP Call-ID → ARI channel id via the pump, and are
idempotent on ``command_id``."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from integrations.telephony_sip.adapter import SipNotConfiguredError, SipTelephonyProvider
from integrations.telephony_sip.ari import AriClient, AriConfig


def _client(handler: Any) -> AriClient:
    return AriClient(
        AriConfig(host="pbx.test", username="bbz", password="s3cret"),
        transport=httpx.MockTransport(handler),
    )


async def _tracked_provider(calls: list[str]) -> SipTelephonyProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        if request.url.path == "/ari/channels" and request.method == "POST":
            return httpx.Response(
                200, json={"id": "ari-ch-9", "channelvars": {"SIPCALLID": "out-call@pbx"}}
            )
        if request.url.path == "/ari/bridges" and request.method == "POST":
            return httpx.Response(200, json={"id": "bridge-1"})
        return httpx.Response(204)

    p = SipTelephonyProvider(ari=_client(handler), line_endpoints={"line1": "PJSIP/line1"})
    # simulate the pump having seen an inbound call
    p._channels["in-call@pbx"] = "ari-ch-1"
    return p


async def test_verbs_hit_the_right_ari_channel_endpoints() -> None:
    calls: list[str] = []
    p = await _tracked_provider(calls)

    assert (await p.answer(call_id="in-call@pbx", command_id="c1")).accepted
    assert (await p.hold(call_id="in-call@pbx", command_id="c2")).accepted
    assert (await p.resume(call_id="in-call@pbx", command_id="c3")).accepted
    assert (await p.hangup(call_id="in-call@pbx", command_id="c4")).accepted

    assert "POST /ari/channels/ari-ch-1/answer?" in calls
    assert "POST /ari/channels/ari-ch-1/hold?" in calls
    assert "POST /ari/channels/ari-ch-1/unhold?" in calls
    assert "POST /ari/channels/ari-ch-1/hangup?" in calls
    await p.shutdown()


async def test_command_id_is_idempotent_and_does_not_hit_the_gateway_twice() -> None:
    calls: list[str] = []
    p = await _tracked_provider(calls)

    first = await p.answer(call_id="in-call@pbx", command_id="same")
    before = len(calls)
    second = await p.answer(call_id="in-call@pbx", command_id="same")
    assert first == second
    assert len(calls) == before  # replayed from the cache
    await p.shutdown()


async def test_an_untracked_call_is_rejected_not_raised() -> None:
    p = await _tracked_provider([])
    ack = await p.hangup(call_id="ghost@pbx", command_id="c")
    assert ack.accepted is False and ack.detail == "call not tracked"
    await p.shutdown()


async def test_dial_originates_and_starts_tracking_the_new_call() -> None:
    calls: list[str] = []
    p = await _tracked_provider(calls)

    ack = await p.dial(line_id="line1", destination="2001", command_id="d1")
    assert ack.accepted and ack.call_id == "out-call@pbx"
    assert p._channels["out-call@pbx"] == "ari-ch-9"
    orig = next(c for c in calls if "/ari/channels?" in c)
    assert "endpoint=PJSIP" in orig and "extension=2001" in orig
    await p.shutdown()


async def test_blind_transfer_redirects_the_channel() -> None:
    calls: list[str] = []
    p = await _tracked_provider(calls)
    ack = await p.transfer(call_id="in-call@pbx", destination="line1", command_id="t1")
    assert ack.accepted and ack.detail == "blind transfer"
    assert any("redirect?endpoint=PJSIP%2Fline1" in c for c in calls)
    await p.shutdown()


async def test_conference_bridges_two_tracked_calls() -> None:
    calls: list[str] = []
    p = await _tracked_provider(calls)
    p._channels["other@pbx"] = "ari-ch-2"
    ack = await p.conference(call_ids=["in-call@pbx", "other@pbx"], command_id="cf1")
    assert ack.accepted and "bridge-1" in (ack.detail or "")
    assert "POST /ari/bridges?type=mixing" in calls
    assert any("/ari/bridges/bridge-1/addChannel?channel=ari-ch-1" in c for c in calls)
    assert any("/ari/bridges/bridge-1/addChannel?channel=ari-ch-2" in c for c in calls)
    await p.shutdown()


async def test_conference_needs_two_tracked_calls() -> None:
    p = await _tracked_provider([])
    ack = await p.conference(call_ids=["in-call@pbx"], command_id="cf")
    assert ack.accepted is False and ack.detail == "need 2 calls"
    await p.shutdown()


async def test_verbs_still_raise_without_a_gateway() -> None:
    p = SipTelephonyProvider()
    for call in (
        lambda: p.answer(call_id="x", command_id="c"),
        lambda: p.dial(line_id="l", destination="2", command_id="c"),
        lambda: p.transfer(call_id="x", destination="9", command_id="c"),
        lambda: p.conference(call_ids=["x", "y"], command_id="c"),
        lambda: p.send_dtmf(call_id="x", dtmf="1", command_id="c"),
    ):
        with pytest.raises(SipNotConfiguredError):
            await call()
