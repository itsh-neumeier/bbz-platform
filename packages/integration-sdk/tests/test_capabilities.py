from __future__ import annotations

import pytest

from bbz_integration_sdk.capabilities import (
    Capability,
    CapabilityNotSupported,
    CapabilitySet,
)


def test_membership_and_iteration() -> None:
    cs = CapabilitySet([Capability.CALL_ANSWER, "call.hangup"])
    assert cs.has(Capability.CALL_ANSWER)
    assert cs.has("call.hangup")
    assert not cs.has(Capability.CALL_TRANSFER)
    assert len(cs) == 2
    assert list(cs) == ["call.answer", "call.hangup"]


def test_unknown_capability_is_false_not_error() -> None:
    cs = CapabilitySet([Capability.CALL_ANSWER])
    assert cs.has("does.not.exist") is False


def test_require_raises_for_missing() -> None:
    cs = CapabilitySet([Capability.CALL_ANSWER])
    cs.require(Capability.CALL_ANSWER)
    with pytest.raises(CapabilityNotSupported):
        cs.require(Capability.MEDIA_TERMINATION)


def test_equality() -> None:
    assert CapabilitySet(["call.answer"]) == CapabilitySet([Capability.CALL_ANSWER])
