"""Mock Coda Video provider: video presentation + alarm ingress.

Every simulated alarm is emitted with a stable ``provider_event_id`` so the
(future) provider-event inbox can dedupe it — a duplicated panic alarm must never
create two BBZ events (ADR-0006 HA rule). The mock itself does no deduplication;
it just guarantees a stable identity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo


def normalize_alarm(raw: dict[str, Any], *, instance_id: str) -> dict[str, Any]:
    """Translate a simulated raw alarm into the BBZ normalized provider event.

    The raw payload shape here is the MOCK's own invention for testing and is not
    a claim about the real Coda API.
    """
    return {
        "provider": "coda_video",
        "provider_instance_id": instance_id,
        "provider_event_id": raw["id"],
        "alarm_type": raw.get("type", "technical_alarm"),
        "alarm_subtype": raw.get("subtype"),
        "source_external_id": raw["source"],
        "source_name": raw.get("source_name", raw["source"]),
        "site_external_id": raw.get("site"),
        "occurred_at": raw.get("occurred_at") or datetime.now(UTC).isoformat(),
        "received_at": datetime.now(UTC).isoformat(),
        "severity_external": raw.get("severity"),
        "associated_cameras": list(raw.get("cameras", [])),
        "raw_ref": raw["id"],
    }


class MockCodaVideoProvider:
    def __init__(
        self,
        *,
        instance_id: str = "coda-mock-1",
        simulated_sources: list[dict[str, Any]] | None = None,
    ) -> None:
        self._instance_id = instance_id
        self._sources = {s["external_source_id"]: s for s in (simulated_sources or [])}
        self._pending: list[dict[str, Any]] = []

    async def initialize(self) -> None:
        return None

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="coda_video",
            provider="mock",
            instance_id=self._instance_id,
            mock=True,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            [
                Capability.VIDEO_RESOLVE_CAMERA,
                Capability.VIDEO_OPEN_CAMERA,
                Capability.VIDEO_OPEN_CAMERA_GROUP,
                Capability.ALARM_SUBSCRIBE,
                Capability.ALARM_RESOLVE_SOURCE,
                Capability.ALARM_GET_CONTEXT,
            ]
        )

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            integration_id="coda_video",
            state=HealthState.HEALTHY,
            summary="mock",
            details={"sources": len(self._sources), "pending_alarms": len(self._pending)},
        )

    async def shutdown(self) -> None:
        self._pending.clear()

    # --- test/simulation helper (not part of the provider protocol) ---
    def simulate_alarm(self, raw: dict[str, Any]) -> dict[str, Any]:
        event = normalize_alarm(raw, instance_id=self._instance_id)
        self._pending.append(event)
        return event

    # --- video ---
    async def resolve_camera(self, *, external_id: str) -> dict[str, Any]:
        return {"camera_id": external_id, "resolved": True}

    async def open_camera(
        self, *, camera_id: str, workplace_id: str, command_id: str
    ) -> dict[str, Any]:
        return {"camera_id": camera_id, "workplace_id": workplace_id, "opened": True}

    async def open_camera_group(
        self, *, camera_ids: list[str], workplace_id: str, command_id: str
    ) -> dict[str, Any]:
        return {"camera_ids": camera_ids, "opened": True}

    async def open_alarm_context(
        self, *, alarm_ref: str, workplace_id: str, command_id: str
    ) -> dict[str, Any]:
        return {"alarm_ref": alarm_ref, "opened": True}

    # --- alarm ingress ---
    async def subscribe_alarms(self) -> AsyncIterator[dict[str, Any]]:
        while self._pending:
            yield self._pending.pop(0)

    async def resolve_source(self, *, external_source_id: str) -> dict[str, Any] | None:
        return self._sources.get(external_source_id)

    async def get_context(self, *, provider_event_id: str) -> dict[str, Any]:
        return {"provider_event_id": provider_event_id}

    async def get_associated_cameras(self, *, provider_event_id: str) -> list[str]:
        return []
