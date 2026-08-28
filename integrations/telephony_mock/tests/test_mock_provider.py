from __future__ import annotations

from bbz_integration_sdk.capabilities import Capability
from bbz_integration_sdk.providers import TelephonyProvider
from integrations.telephony_mock.adapter import MockTelephonyProvider


def test_satisfies_protocol() -> None:
    assert isinstance(MockTelephonyProvider(), TelephonyProvider)


async def test_call_lifecycle() -> None:
    p = MockTelephonyProvider(lines=["2001"])
    await p.initialize()

    call = await p.dial(line_id="2001", destination="112", command_id="c1")
    assert call["state"] == "CALL_RINGING"
    cid = call["call_id"]

    answered = await p.answer(call_id=cid, command_id="c2")
    assert answered["state"] == "CALL_ANSWERED"

    assert len(await p.get_active_calls()) == 1

    ended = await p.hangup(call_id=cid, command_id="c3")
    assert ended["state"] == "CALL_DISCONNECTED"
    assert await p.get_active_calls() == []


async def test_send_dtmf_does_not_leak_code() -> None:
    p = MockTelephonyProvider()
    result = await p.send_dtmf(call_id="x", dtmf_profile_id="door-profile-1", command_id="c")
    assert result["dtmf_profile_id"] == "door-profile-1"
    assert "code" not in result
    assert "dtmf_code" not in result


async def test_capabilities_are_feature_detectable() -> None:
    caps = MockTelephonyProvider().capabilities()
    assert caps.has(Capability.CALL_ANSWER)
    assert not caps.has(Capability.CALL_CONFERENCE)
