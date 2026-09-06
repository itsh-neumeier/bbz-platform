"""``telephony_sip`` against a live Asterisk (roadmap E13-08, ADR-0023).

Integration scenarios against the ``sip`` compose-profile lab PBX
(``deploy/sip/``): an incoming call through the Stasis app, answer / hold /
resume / DTMF / hangup, an outbound ``dial``, blind transfer, and the health
probe — the full ``TelephonyProvider`` surface E13-03..06 built, exercised end
to end against real ARI instead of ``httpx.MockTransport``.

Skipped unless an ARI endpoint answers on ``BBZ_TEST_ARI_HOST``:``BBZ_TEST_ARI_PORT``
(default ``127.0.0.1:8088``). Run nightly by ``.github/workflows/sip-nightly.yml``
(``continue-on-error`` until shaken out on real hardware — same policy as the HA
harness).
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import AsyncIterator

import pytest

from bbz_integration_sdk.diagnostics import HealthState
from bbz_integration_sdk.normalized_events import NormalizedTelephonyEvent as Ev
from bbz_integration_sdk.providers.telephony_types import CallEvent
from integrations.telephony_sip.adapter import SipTelephonyProvider
from integrations.telephony_sip.ari import AriClient, AriConfig

_HOST = os.environ.get("BBZ_TEST_ARI_HOST", "127.0.0.1")
_PORT = int(os.environ.get("BBZ_TEST_ARI_PORT", "8088"))
_USER = os.environ.get("BBZ_TEST_ARI_USER", "bbz-lab")
_PASSWORD = os.environ.get("BBZ_TEST_ARI_PASSWORD", "bbz-lab-not-a-secret")
_APP = "bbz-sip"
_DTMF = "1234#"  # a stand-in for the resolved door secret (ADR-0025)


def _ari_up() -> bool:
    try:
        with socket.create_connection((_HOST, _PORT), timeout=2):
            return True
    except OSError:
        return False


if not _ari_up():  # pragma: no cover - depends on the environment
    pytest.skip("no lab Asterisk ARI reachable", allow_module_level=True)


def _config(**over: object) -> AriConfig:
    base: dict[str, object] = {
        "host": _HOST,
        "port": _PORT,
        "username": _USER,
        "password": _PASSWORD,
        "app_name": _APP,
        "timeout": 5.0,
    }
    base.update(over)
    return AriConfig(**base)  # type: ignore[arg-type]


@pytest.fixture
async def provider() -> AsyncIterator[SipTelephonyProvider]:
    p = SipTelephonyProvider(
        line_endpoints={"lab": "Local/park@bbz-lab"},
        ari=AriClient(_config()),
    )
    await p.initialize()
    for _ in range(50):  # let the pump open the event WebSocket
        if p._ari is not None and p._ari.ws.connected:
            break
        await asyncio.sleep(0.1)
    try:
        yield p
    finally:
        for cid in list(p._channels):  # hang up anything the test left live
            await p.hangup(call_id=cid, command_id=f"cleanup-{cid}")
        await p.shutdown()


async def _drain_until(
    p: SipTelephonyProvider, want: Ev, *, timeout: float = 15.0
) -> tuple[list[CallEvent], list[CallEvent]]:
    """Poll the pump until a ``want`` event appears (or time out). Returns
    ``(matching, everything-seen-so-far)``."""
    seen: list[CallEvent] = []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        seen.extend(await p.drain_events())
        hits = [e for e in seen if e.event_type is want]
        if hits:
            return hits, seen
        await asyncio.sleep(0.2)
    return [], seen


async def _place_inbound(p: SipTelephonyProvider) -> str:
    """Hand a call to the Stasis app the way the PBX would, and return its
    ``source_call_id`` once the pump has surfaced ``CALL_RINGING``. The far leg
    (``park@bbz-lab``) just answers and waits so the near leg can be driven
    entirely over ARI; ``/n`` keeps the Local channel from optimizing away."""
    assert p._ari is not None
    await p._ari.originate(endpoint="Local/park@bbz-lab/n", app=_APP)
    ringing, seen = await _drain_until(p, Ev.CALL_RINGING)
    assert ringing, f"no CALL_RINGING after originate; saw {[e.event_type.value for e in seen]}"
    call_id = ringing[0].source_call_id
    assert call_id and ringing[0].metadata.get("direction") == "inbound"
    return call_id


async def test_ari_reachable_and_health_is_green(provider: SipTelephonyProvider) -> None:
    assert provider._ari is not None
    info = await provider._ari.info()
    assert isinstance(info, dict) and info
    report = await provider.health()
    assert report.state in (HealthState.HEALTHY, HealthState.DEGRADED)


async def test_incoming_call_answer_hold_resume_hangup(provider: SipTelephonyProvider) -> None:
    call_id = await _place_inbound(provider)

    assert (await provider.answer(call_id=call_id, command_id="ans-1")).accepted

    assert (await provider.hold(call_id=call_id, command_id="hold-1")).accepted
    held, seen = await _drain_until(provider, Ev.CALL_HELD)
    assert held, f"no CALL_HELD; saw {[e.event_type.value for e in seen]}"

    assert (await provider.resume(call_id=call_id, command_id="res-1")).accepted
    resumed, _ = await _drain_until(provider, Ev.CALL_RESUMED)
    assert resumed

    assert (await provider.hangup(call_id=call_id, command_id="hup-1")).accepted
    gone, seen = await _drain_until(provider, Ev.CALL_DISCONNECTED)
    assert gone, f"no CALL_DISCONNECTED; saw {[e.event_type.value for e in seen]}"
    assert call_id not in provider._channels  # the pump untracked it


async def test_command_id_is_idempotent_against_a_real_gateway(
    provider: SipTelephonyProvider,
) -> None:
    call_id = await _place_inbound(provider)
    first = await provider.answer(call_id=call_id, command_id="dup")
    second = await provider.answer(call_id=call_id, command_id="dup")
    assert first == second  # replayed from the cache, gateway hit once


async def test_send_dtmf_is_accepted_and_never_echoes_the_code(
    provider: SipTelephonyProvider,
) -> None:
    call_id = await _place_inbound(provider)
    await provider.answer(call_id=call_id, command_id="ans-2")

    ack = await provider.send_dtmf(call_id=call_id, dtmf=_DTMF, command_id="dtmf-1")
    assert ack.accepted
    assert _DTMF not in (ack.detail or "") and "1234" not in (ack.detail or "")

    replay = await provider.send_dtmf(call_id=call_id, dtmf=_DTMF, command_id="dtmf-1")
    assert replay == ack  # not re-emitted


async def test_outbound_dial_tracks_the_new_channel(provider: SipTelephonyProvider) -> None:
    ack = await provider.dial(line_id="lab", destination="3000", command_id="dial-1")
    assert ack.accepted and ack.call_id
    assert ack.call_id in provider._channels

    for _ in range(30):
        if any(c.call_id == ack.call_id for c in await provider.get_active_calls()):
            break
        await asyncio.sleep(0.2)
    else:
        pytest.fail("dialled channel never showed up in get_active_calls()")


async def test_blind_transfer_is_accepted(provider: SipTelephonyProvider) -> None:
    call_id = await _place_inbound(provider)
    await provider.answer(call_id=call_id, command_id="ans-3")
    ack = await provider.transfer(call_id=call_id, destination="lab", command_id="xfer-1")
    assert ack.accepted and ack.detail == "blind transfer"


async def test_health_is_unavailable_when_the_gateway_is_unreachable() -> None:
    dead = SipTelephonyProvider(ari=AriClient(_config(port=1)))
    report = await dead.health()
    assert report.state is HealthState.UNAVAILABLE
    await dead.shutdown()
