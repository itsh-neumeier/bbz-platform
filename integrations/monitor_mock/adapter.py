"""``monitor_mock`` — a complete in-memory monitor / KVM routing provider
(roadmap E19-06, MASTER_PROMPT §9 "Provider 1: monitor_mock").

Deterministic: a route is applied to an in-memory map and read straight back. A
repeated ``command_id`` replays the first result without re-applying (idempotency
the routing service relies on, E19-04). Failures are *simulated* via config —
``unreachable_outputs`` makes those outputs reject a route (a real device
reporting a dead sink); ``apply_layout`` is atomic (one bad output → nothing
changes).

This provider is a dumb router: it validates that a port exists and simulates
reachability. BBZ policy — the "lower-left is always BBZ-OS" rule (E19-03) — is
enforced upstream in the domain / routing service, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo

#: default ports — aligned with bbz_core.domain.monitor.catalog so an end-to-end
#: test (E19-10) routes real catalog keys through the mock unchanged.
_DEFAULT_INPUTS = ("bbz-os", "bku1", "bku2", "bku3", "bku4", "coda1", "coda2")
_DEFAULT_OUTPUTS = (
    "workplace1",
    "workplace2",
    "workplace3",
    "workplace4",
    "workplace5",
    "workplace6",
    "large-display",
)


class MonitorMockError(RuntimeError):
    """Base for monitor_mock routing failures."""


class UnknownPortError(MonitorMockError):
    """A route referenced an input or output the device does not have."""


class OutputUnreachableError(MonitorMockError):
    """A (simulated) output is not reachable and cannot be switched."""


@dataclass
class MockConfig:
    inputs: tuple[str, ...] = _DEFAULT_INPUTS
    outputs: tuple[str, ...] = _DEFAULT_OUTPUTS
    #: outputs that reject any route (simulated hardware fault)
    unreachable_outputs: frozenset[str] = frozenset()
    instance_id: str = "mock"
    initial_routes: dict[str, str] = field(default_factory=dict)


class MockMonitorProvider:
    def __init__(self, config: MockConfig | None = None) -> None:
        self._cfg = config or MockConfig()
        self._inputs = tuple(self._cfg.inputs)
        self._outputs = tuple(self._cfg.outputs)
        self._unreachable = frozenset(self._cfg.unreachable_outputs)
        self._routes: dict[str, str] = dict(self._cfg.initial_routes)
        #: command_id -> the result it produced (idempotent replay)
        self._commands: dict[str, dict[str, Any]] = {}
        self._initialized = False

    # --- lifecycle -----------------------------------------------------

    async def initialize(self) -> None:
        self._initialized = True

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="monitor_mock",
            provider="mock",
            instance_id=self._cfg.instance_id,
            mock=True,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet([Capability.MONITOR_ROUTE, Capability.MONITOR_LAYOUT_PROFILES])

    async def health(self) -> DiagnosticsReport:
        degraded = bool(self._unreachable)
        return DiagnosticsReport(
            integration_id="monitor_mock",
            state=HealthState.DEGRADED if degraded else HealthState.HEALTHY,
            summary=(
                f"{len(self._unreachable)} output(s) unreachable"
                if degraded
                else "all outputs reachable"
            ),
            details={
                "inputs": len(self._inputs),
                "outputs": len(self._outputs),
                "routed": len(self._routes),
                "unreachable": ", ".join(sorted(self._unreachable)),
            },
        )

    async def shutdown(self) -> None:
        self._initialized = False

    # --- reads --------------------------------------------------------

    async def list_inputs(self) -> list[dict[str, Any]]:
        return [{"input_id": i, "label": i} for i in self._inputs]

    async def list_outputs(self) -> list[dict[str, Any]]:
        return [
            {"output_id": o, "label": o, "reachable": o not in self._unreachable}
            for o in self._outputs
        ]

    async def get_routes(self) -> list[dict[str, Any]]:
        return [
            {"output_id": o, "input_id": self._routes[o]}
            for o in self._outputs
            if o in self._routes
        ]

    # --- writes ------------------------------------------------------

    async def set_route(self, *, output_id: str, input_id: str, command_id: str) -> dict[str, Any]:
        if command_id in self._commands:
            return self._commands[command_id]  # idempotent replay
        self._check_ports(output_id, input_id)
        if output_id in self._unreachable:
            raise OutputUnreachableError(f"output {output_id!r} is not reachable")
        self._routes[output_id] = input_id
        result = {"output_id": output_id, "input_id": input_id, "applied": True}
        self._commands[command_id] = result
        return result

    async def apply_layout(self, *, layout: dict[str, str], command_id: str) -> dict[str, Any]:
        if command_id in self._commands:
            return self._commands[command_id]
        for output_id, input_id in layout.items():
            self._check_ports(output_id, input_id)
            if output_id in self._unreachable:
                raise OutputUnreachableError(
                    f"output {output_id!r} is not reachable — layout not applied"
                )
        self._routes.update(layout)  # atomic: all checks passed first
        result = {"applied": sorted(layout), "routes": dict(self._routes)}
        self._commands[command_id] = result
        return result

    # --- helpers ---------------------------------------------------

    def _check_ports(self, output_id: str, input_id: str) -> None:
        if output_id not in self._outputs:
            raise UnknownPortError(f"unknown output {output_id!r}")
        if input_id not in self._inputs:
            raise UnknownPortError(f"unknown input {input_id!r}")


def build(config: dict[str, Any] | None = None) -> MockMonitorProvider:
    """Manifest entry point."""
    cfg = config or {}
    return MockMonitorProvider(
        MockConfig(
            inputs=tuple(cfg.get("inputs") or _DEFAULT_INPUTS),
            outputs=tuple(cfg.get("outputs") or _DEFAULT_OUTPUTS),
            unreachable_outputs=frozenset(cfg.get("unreachable_outputs") or ()),
            instance_id=cfg.get("instance_id", "mock"),
            initial_routes=dict(cfg.get("initial_routes") or {}),
        )
    )
