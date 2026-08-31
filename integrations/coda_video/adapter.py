"""Mock Coda Video provider: video presentation + alarm ingress.

A deterministic simulation of the ``coda_video`` (HxGN dC3 Video) integration for
tests and local dev (E16-09) — no vendor API is touched. It covers the
``.ai/INTEGRATIONS_CODA_VIDEO.md`` "Testing" list:

* panic / intrusion / generic technical alarms (``simulate_alarm``);
* one or several associated cameras per alarm (``get_associated_cameras``);
* an unmapped source (``resolve_source`` -> ``None``);
* a duplicated alarm (same ``provider_event_id`` emitted twice);
* a reconnect that replays the backlog (``reconnect``);
* a camera whose open / focus operation fails (``camera_failures`` / ``fail_cameras``).

Every simulated alarm carries a stable ``provider_event_id`` so the provider-event
inbox can dedupe it — a duplicated panic alarm must never create two BBZ events
(ADR-0006). The mock itself does no deduplication; it guarantees identity.
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
    CameraOpenFailed,
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
        camera_failures: list[str] | None = None,
    ) -> None:
        self._instance_id = instance_id
        groups = enabled_capability_groups or list(_CAPABILITY_GROUPS)
        unknown = sorted(set(groups) - set(_CAPABILITY_GROUPS))
        if unknown:
            raise ValueError(f"unknown capability group(s): {unknown}")
        self._groups = tuple(g for g in _CAPABILITY_GROUPS if g in groups)
        self._sources = {s["external_source_id"]: s for s in (simulated_sources or [])}
        self._pending: list[IncomingAlarm] = []
        #: alarms already handed to a subscriber — replayed on reconnect()
        self._delivered: list[IncomingAlarm] = []
        #: provider_event_id -> the cameras the alarm is associated with
        self._alarm_cameras: dict[str, list[str]] = {}
        #: camera refs whose open / focus operations fail
        self._camera_failures: set[str] = set(camera_failures or [])

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
            details={
                "sources": len(self._sources),
                "pending_alarms": len(self._pending),
                "delivered_alarms": len(self._delivered),
                "failing_cameras": ", ".join(sorted(self._camera_failures)),
            },
        )

    async def shutdown(self) -> None:
        self._pending.clear()

    # --- test / simulation helpers (not part of the provider protocol) ---

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
        key = alarm.provider_event_id or f"anon-{len(self._alarm_cameras)}"
        self._alarm_cameras[key] = list(alarm.associated_camera_ids)
        self._pending.append(alarm)
        return alarm

    def reconnect(self) -> None:
        """Model a provider reconnect: the backlog it already delivered is
        replayed to the next subscriber (an active/active reconnect must not
        create duplicate events — the inbox dedupes, E16-04)."""
        self._pending = [*self._delivered, *self._pending]
        self._delivered.clear()

    def fail_cameras(self, *camera_refs: str) -> None:
        self._camera_failures.update(camera_refs)

    def clear_camera_failures(self) -> None:
        self._camera_failures.clear()

    # --- video ---

    def _all_camera_ids(self) -> set[str]:
        ids: set[str] = set()
        for src in self._sources.values():
            ids.update(src.get("cameras", []))
        return ids

    def _guard_cameras(self, *camera_ids: str) -> None:
        bad = sorted(c for c in camera_ids if c in self._camera_failures)
        if bad:
            raise CameraOpenFailed(f"camera operation failed for {bad}")

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
        self._guard_cameras(camera_id)
        return CameraView(
            camera_id=camera_id,
            workplace_id=workplace_id,
            command_id=command_id,
            action="opened",
        )

    async def focus_camera(
        self, *, camera_id: str, workplace_id: str, command_id: str, preset: str | None = None
    ) -> CameraView:
        self._guard_cameras(camera_id)
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
        self._guard_cameras(*camera_ids)
        return CameraGroupView(
            camera_ids=list(camera_ids), workplace_id=workplace_id, command_id=command_id
        )

    async def open_alarm_context(
        self, *, alarm_ref: str, workplace_id: str, command_id: str
    ) -> AlarmContextView:
        cams = sorted(self._all_camera_ids())
        self._guard_cameras(*cams)
        return AlarmContextView(
            alarm_ref=alarm_ref,
            workplace_id=workplace_id,
            command_id=command_id,
            camera_ids=cams,
        )

    # --- alarm ingress ---

    async def subscribe_alarms(self) -> AsyncIterator[IncomingAlarm]:
        while self._pending:
            alarm = self._pending.pop(0)
            self._delivered.append(alarm)
            yield alarm

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
        return list(self._alarm_cameras.get(provider_event_id, []))


def build(config: dict[str, Any] | None = None) -> MockCodaVideoProvider:
    """Construct the mock provider from validated ``config_schema.json`` config."""
    cfg = config or {}
    return MockCodaVideoProvider(
        instance_id=cfg.get("instance_id", "coda-mock-1"),
        enabled_capability_groups=cfg.get("enabled_capability_groups"),
        simulated_sources=cfg.get("simulated_sources"),
        camera_failures=cfg.get("camera_failures"),
    )
