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
from bbz_integration_sdk.providers.alarm_types import AlarmContext, AlarmSource, IncomingAlarm
from bbz_integration_sdk.providers.base import ProviderInfo
from bbz_integration_sdk.providers.video_types import (
    AlarmContextView,
    CameraGroupView,
    CameraNotFoundError,
    CameraView,
    ResolvedCamera,
)

#: the two independent capability groups (E16-01) — see manifest.json
_CAPABILITY_GROUPS: dict[str, tuple[Capability, ...]] = {
    "video": (
        Capability.VIDEO_RESOLVE_CAMERA,
        Capability.VIDEO_OPEN_CAMERA,
        Capability.VIDEO_FOCUS_CAMERA,
        Capability.VIDEO_OPEN_CAMERA_GROUP,
        Capability.VIDEO_OPEN_ALARM_CONTEXT,
    ),
    "alarm_ingress": (
        Capability.ALARM_SUBSCRIBE,
        Capability.ALARM_RESOLVE_SOURCE,
        Capability.ALARM_GET_CONTEXT,
        Capability.ALARM_GET_ASSOCIATED_CAMERAS,
    ),
}


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
        enabled_capability_groups: list[str] | None = None,
        simulated_sources: list[dict[str, Any]] | None = None,
    ) -> None:
        self._instance_id = instance_id
        groups = enabled_capability_groups or list(_CAPABILITY_GROUPS)
        unknown = sorted(set(groups) - set(_CAPABILITY_GROUPS))
        if unknown:
            raise ValueError(f"unknown capability group(s): {unknown}")
        self._groups = tuple(g for g in _CAPABILITY_GROUPS if g in groups)
        self._sources = {s["external_source_id"]: s for s in (simulated_sources or [])}
        self._pending: list[IncomingAlarm] = []

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
        return CapabilitySet([cap for group in self._groups for cap in _CAPABILITY_GROUPS[group]])

    def enabled_capability_groups(self) -> tuple[str, ...]:
        return self._groups

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
    def simulate_alarm(self, raw: dict[str, Any]) -> IncomingAlarm:
        alarm = IncomingAlarm(
            provider="coda_video",
            provider_instance_id=self._instance_id,
            provider_event_id=raw.get("id"),
            alarm_type=raw.get("type", "technical_alarm"),
            alarm_subtype=raw.get("subtype"),
            source_external_id=raw["source"],
            source_name=raw.get("source_name"),
            site_external_id=raw.get("site"),
            occurred_at=raw.get("occurred_at"),
            received_at=datetime.now(UTC),
            severity_external=raw.get("severity"),
            state_external=raw.get("state"),
            associated_camera_ids=list(raw.get("cameras", [])),
            raw=dict(raw),
        )
        self._pending.append(alarm)
        return alarm

    # --- video ---
    def _all_camera_ids(self) -> set[str]:
        ids: set[str] = set()
        for src in self._sources.values():
            ids.update(src.get("cameras", []))
        return ids

    async def resolve_camera(self, *, external_id: str) -> ResolvedCamera:
        if external_id not in self._all_camera_ids():
            raise CameraNotFoundError(external_id)
        for src in self._sources.values():
            if external_id in src.get("cameras", []):
                return ResolvedCamera(
                    camera_id=external_id,
                    name=f"{src['name']} / {external_id}",
                    site=src.get("site"),
                    group_ids=[src["external_source_id"]],
                )
        raise CameraNotFoundError(external_id)  # pragma: no cover — unreachable

    async def open_camera(
        self, *, camera_id: str, workplace_id: str, command_id: str
    ) -> CameraView:
        return CameraView(
            camera_id=camera_id,
            workplace_id=workplace_id,
            command_id=command_id,
            action="opened",
        )

    async def focus_camera(
        self, *, camera_id: str, workplace_id: str, command_id: str, preset: str | None = None
    ) -> CameraView:
        return CameraView(
            camera_id=camera_id,
            workplace_id=workplace_id,
            command_id=command_id,
            action="focused",
            preset=preset,
        )

    async def open_camera_group(
        self, *, camera_ids: list[str], workplace_id: str, command_id: str
    ) -> CameraGroupView:
        return CameraGroupView(
            camera_ids=list(camera_ids), workplace_id=workplace_id, command_id=command_id
        )

    async def open_alarm_context(
        self, *, alarm_ref: str, workplace_id: str, command_id: str
    ) -> AlarmContextView:
        cams = sorted(self._all_camera_ids())
        return AlarmContextView(
            alarm_ref=alarm_ref,
            workplace_id=workplace_id,
            command_id=command_id,
            camera_ids=cams,
        )

    # --- alarm ingress ---
    async def subscribe_alarms(self) -> AsyncIterator[IncomingAlarm]:
        while self._pending:
            yield self._pending.pop(0)

    async def resolve_source(self, *, external_source_id: str) -> AlarmSource | None:
        src = self._sources.get(external_source_id)
        if src is None:
            return None
        return AlarmSource(
            external_source_id=external_source_id,
            name=src.get("name"),
            site_external_id=src.get("site"),
            associated_camera_ids=list(src.get("cameras", [])),
        )

    async def get_context(self, *, provider_event_id: str) -> AlarmContext:
        return AlarmContext(
            provider_event_id=provider_event_id,
            associated_camera_ids=await self.get_associated_cameras(
                provider_event_id=provider_event_id
            ),
        )

    async def get_associated_cameras(self, *, provider_event_id: str) -> list[str]:
        return []


def build(config: dict[str, Any] | None = None) -> MockCodaVideoProvider:
    """Construct the mock provider from validated ``config_schema.json`` config."""
    cfg = config or {}
    return MockCodaVideoProvider(
        instance_id=cfg.get("instance_id", "coda-mock-1"),
        enabled_capability_groups=cfg.get("enabled_capability_groups"),
        simulated_sources=cfg.get("simulated_sources"),
    )
