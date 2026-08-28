"""The provider protocols are structural. This test proves a minimal in-memory
implementation satisfies the runtime-checkable protocol, so integrations have a
concrete conformance target from day one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers import TelephonyProvider
from bbz_integration_sdk.providers.base import ProviderInfo


class _MiniTelephony:
    def __init__(self) -> None:
        self._info = ProviderInfo(
            integration_id="telephony_mock",
            provider="mock",
            instance_id="test",
            mock=True,
        )

    async def initialize(self) -> None: ...

    def info(self) -> ProviderInfo:
        return self._info

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet([Capability.CALL_ANSWER, Capability.CALL_HANGUP])

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(integration_id="telephony_mock", state=HealthState.HEALTHY)

    async def shutdown(self) -> None: ...

    async def list_lines(self) -> list[object]:
        return []

    async def get_line_state(self, line_id: str) -> object:
        return {"line_id": line_id, "state": "in_service"}

    async def get_active_calls(self) -> list[object]:
        return []

    async def subscribe_call_events(self) -> AsyncIterator[object]:
        if False:  # pragma: no cover - empty async generator
            yield None

    async def dial(self, *, line_id: str, destination: str, command_id: str) -> object:
        return {"call_id": "c1"}

    async def answer(self, *, call_id: str, command_id: str) -> object:
        return {"call_id": call_id, "state": "answered"}

    async def hangup(self, *, call_id: str, command_id: str) -> object:
        return {"call_id": call_id, "state": "disconnected"}

    async def hold(self, *, call_id: str, command_id: str) -> object:
        return {}

    async def resume(self, *, call_id: str, command_id: str) -> object:
        return {}

    async def transfer(self, *, call_id: str, destination: str, command_id: str) -> object:
        return {}

    async def conference(self, *, call_ids: list[str], command_id: str) -> object:
        return {}

    async def send_dtmf(self, *, call_id: str, dtmf_profile_id: str, command_id: str) -> object:
        return {}

    async def resolve_caller(self, *, number: str) -> object:
        return None

    async def reconcile(self) -> object:
        return {"reconciled": True}


def test_mini_implementation_satisfies_protocol() -> None:
    provider = _MiniTelephony()
    assert isinstance(provider, TelephonyProvider)


async def test_capability_gate() -> None:
    provider = _MiniTelephony()
    caps = provider.capabilities()
    assert caps.has(Capability.CALL_ANSWER)
    assert not caps.has(Capability.CALL_CONFERENCE)
    report = await provider.health()
    assert report.state is HealthState.HEALTHY
