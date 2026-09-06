"""SIP send_dtmf over ARI (E13-06). The DTMF sequence is the resolved door-open
secret (ADR-0025) — it goes straight to ``channels/{id}/dtmf`` and must never
appear in a log, the ack detail, or an error (ADR-0004). Idempotent: a replayed
command is not re-emitted."""

from __future__ import annotations

import httpx
import pytest

from integrations.telephony_sip.adapter import SipNotConfiguredError, SipTelephonyProvider
from integrations.telephony_sip.ari import AriClient, AriConfig

_SECRET = "4711#"


def _provider(calls: list[str]) -> SipTelephonyProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        return httpx.Response(204)

    ari = AriClient(
        AriConfig(host="pbx.test", username="bbz", password="s3cret"),
        transport=httpx.MockTransport(handler),
    )
    p = SipTelephonyProvider(ari=ari)
    p._channels["door@pbx"] = "ari-ch-door"
    return p


async def test_dtmf_is_emitted_on_the_channel_and_acked_without_the_code() -> None:
    calls: list[str] = []
    p = _provider(calls)
    ack = await p.send_dtmf(call_id="door@pbx", dtmf=_SECRET, command_id="d1")
    assert ack.accepted and ack.detail == "dtmf sent"
    assert _SECRET not in (ack.detail or "")
    assert any(c.startswith("POST /ari/channels/ari-ch-door/dtmf?") for c in calls)
    await p.shutdown()


async def test_a_replayed_command_is_not_re_emitted() -> None:
    calls: list[str] = []
    p = _provider(calls)
    first = await p.send_dtmf(call_id="door@pbx", dtmf=_SECRET, command_id="same")
    n = len(calls)
    second = await p.send_dtmf(call_id="door@pbx", dtmf=_SECRET, command_id="same")
    assert first == second
    assert len(calls) == n  # the door does not open twice
    await p.shutdown()


async def test_a_gateway_error_never_leaks_the_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"boom dtmf={_SECRET}")

    ari = AriClient(
        AriConfig(host="pbx.test", username="bbz", password="s3cret"),
        transport=httpx.MockTransport(handler),
    )
    p = SipTelephonyProvider(ari=ari)
    p._channels["door@pbx"] = "ari-ch-door"
    ack = await p.send_dtmf(call_id="door@pbx", dtmf=_SECRET, command_id="d")
    assert ack.accepted is False
    assert _SECRET not in (ack.detail or "")
    await p.shutdown()


async def test_untracked_call_is_rejected_and_no_gateway_still_raises() -> None:
    p = _provider([])
    rej = await p.send_dtmf(call_id="ghost@pbx", dtmf=_SECRET, command_id="c")
    assert rej.accepted is False and rej.detail == "call not tracked"
    await p.shutdown()

    with pytest.raises(SipNotConfiguredError):
        await SipTelephonyProvider().send_dtmf(call_id="x", dtmf="1", command_id="c")


def test_send_dtmf_capability_is_advertised() -> None:
    caps = {str(c) for c in SipTelephonyProvider().capabilities()}
    assert any("send_dtmf" in c for c in caps)
