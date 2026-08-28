from __future__ import annotations

from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo

# Business rule from MASTER_PROMPT §9: the lower-left workplace monitor is always
# BBZ-OS. That rule is enforced in the domain layer later; the mock just refuses
# to route it away so tests can assert on it.
LOCKED_OUTPUT = "AP_LOWER_LEFT"
LOCKED_INPUT = "BBZ-OS"


class MockMonitorProvider:
    def __init__(
        self,
        *,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        instance_id: str = "mock",
    ) -> None:
        self._inputs = list(inputs or ["BBZ-OS", "BKU1", "BKU2", "CODA1"])
        self._outputs = list(outputs or ["AP1", "AP2", "AP3", "AP4", "AP5", "AP6", "GROSSBILD"])
        self._instance_id = instance_id
        self._routes: dict[str, str] = {LOCKED_OUTPUT: LOCKED_INPUT}

    async def initialize(self) -> None:
        return None

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="monitor_mock",
            provider="mock",
            instance_id=self._instance_id,
            mock=True,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet([Capability.MONITOR_ROUTE, Capability.MONITOR_LAYOUT_PROFILES])

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(integration_id="monitor_mock", state=HealthState.HEALTHY)

    async def shutdown(self) -> None:
        return None

    async def list_inputs(self) -> list[dict[str, Any]]:
        return [{"input_id": i} for i in self._inputs]

    async def list_outputs(self) -> list[dict[str, Any]]:
        return [{"output_id": o} for o in self._outputs]

    async def get_routes(self) -> list[dict[str, Any]]:
        return [{"output_id": o, "input_id": i} for o, i in self._routes.items()]

    async def set_route(self, *, output_id: str, input_id: str, command_id: str) -> dict[str, Any]:
        if output_id == LOCKED_OUTPUT and input_id != LOCKED_INPUT:
            raise ValueError(f"{LOCKED_OUTPUT} is locked to {LOCKED_INPUT}")
        self._routes[output_id] = input_id
        return {"output_id": output_id, "input_id": input_id}

    async def apply_layout(self, *, layout: Any, command_id: str) -> dict[str, Any]:
        return {"applied": True}
