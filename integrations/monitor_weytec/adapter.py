"""``monitor_weytec`` — interface-only scaffold (roadmap E19-07).

The Weytec monitor / KVM routing API is **not documented** in this repository and
must not be invented (RULES.md, MASTER_PROMPT §9: "Weytec-API nicht erfinden").
This adapter exists so the integration is discoverable and its shape is fixed to
the normalized :class:`bbz_integration_sdk.providers.MonitorProvider`; every
routing call raises :class:`WeytecNotConfiguredError` until official documentation
is supplied and a real adapter is built from it.

See ``docs/integrations/weytec-monitor-pending.md``.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, NoReturn

from bbz_integration_sdk.capabilities import CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo

_PENDING_DOC = "docs/integrations/weytec-monitor-pending.md"


class WeytecNotConfiguredError(NotImplementedError):
    """A Weytec routing method was called on the interface-only scaffold."""


def _pending(method: str) -> NoReturn:
    raise WeytecNotConfiguredError(
        f"monitor_weytec.{method} is not implemented — the Weytec API is an open "
        f"external dependency (see {_PENDING_DOC}); it must not be invented"
    )


class WeytecMonitorProvider:
    """Protocol-shaped stub. Lifecycle is honest (``disabled`` health, no
    capabilities); every data / routing method raises."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._instance_id = (config or {}).get("instance_id", "weytec-1")

    async def initialize(self) -> None:
        return None

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="monitor_weytec",
            provider="weytec",
            instance_id=self._instance_id,
            mock=False,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet([])  # nothing is usable yet

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            integration_id="monitor_weytec",
            state=HealthState.DISABLED,
            summary="interface-only scaffold — Weytec API documentation pending",
            checked_at=_dt.datetime.now(_dt.UTC),
            details={"pending_vendor_documentation": _PENDING_DOC},
        )

    async def shutdown(self) -> None:
        return None

    # --- routing (all raise) ----------------------------------------

    async def list_inputs(self) -> list[Any]:
        _pending("list_inputs")

    async def list_outputs(self) -> list[Any]:
        _pending("list_outputs")

    async def get_routes(self) -> list[Any]:
        _pending("get_routes")

    async def set_route(self, *, output_id: str, input_id: str, command_id: str) -> Any:
        _pending("set_route")

    async def apply_layout(self, *, layout: Any, command_id: str) -> Any:
        _pending("apply_layout")


def build(config: dict[str, Any] | None = None) -> WeytecMonitorProvider:
    return WeytecMonitorProvider(config)
