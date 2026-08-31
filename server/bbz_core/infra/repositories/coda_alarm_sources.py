"""Per-alarm-source admin config (roadmap E16-06).

One place to configure a Coda (or any) external alarm source: it maps an
external source id to a BBZ technical endpoint plus its site, BBZ priority,
popup / EPK / escalation profile, its cameras and the enabled flag
(MASTER_PROMPT §36 / ``.ai/INTEGRATIONS_CODA_VIDEO.md`` "Admin mapping").

A **facade** over E15-10 (``technical_endpoints``) and E16-05
(``integration_camera_mappings``) — no new table. Highly privileged: this
defines automatic critical-event creation, so every write audits
``CODA_ALARM_SOURCE_*`` and the API needs both ``technical_endpoints.manage``
and ``integrations.configure``.

``configure`` is an idempotent upsert keyed by ``external_source_id``. The
default BBZ priority for a ``panic_button`` source is ``critical`` unless the
caller overrides it (§36).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import AuditAction, AuditService
from bbz_core.infra.models.integration_camera_mappings import IntegrationCameraMapping
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint

#: endpoint types an alarm source may be configured as
_SOURCE_TYPES = frozenset({"video_alarm", "panic_button", "bma", "custom"})
_PRIORITIES = frozenset({"critical", "high", "medium", "low"})
_PROVIDER_ID = "coda_video"


class AlarmSourceError(ValueError):
    pass


class AlarmSourceNotFoundError(AlarmSourceError):
    pass


class InvalidAlarmSourceError(AlarmSourceError):
    """A field value is not acceptable (blank id, bad type / priority)."""


@dataclass
class AlarmSourceInput:
    endpoint_name: str
    endpoint_type: str = "video_alarm"
    site: str | None = None
    #: BBZ priority; ``None`` -> ``critical`` for a ``panic_button``, else unset
    priority: str | None = None
    camera_refs: list[str] = field(default_factory=list)
    popup_profile: str | None = None
    workflow_selection_policy: dict[str, Any] | None = None
    escalation_profile: str | None = None
    enabled: bool = True
    provider_instance_id: str | None = None


@dataclass(frozen=True)
class AlarmSourceView:
    external_source_id: str
    endpoint: TechnicalEndpoint
    camera_refs: list[str]


class AlarmSourceConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list_sources(self) -> list[AlarmSourceView]:
        endpoints = (
            (
                await self._s.execute(
                    select(TechnicalEndpoint)
                    .where(TechnicalEndpoint.provider_id == _PROVIDER_ID)
                    .order_by(TechnicalEndpoint.name, TechnicalEndpoint.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        views: list[AlarmSourceView] = []
        for e in endpoints:
            for ext in e.external_source_ids or []:
                views.append(AlarmSourceView(ext, e, await self._cameras(ext)))
        return views

    async def get(self, external_source_id: str) -> AlarmSourceView:
        endpoint = await self._endpoint_for(external_source_id)
        if endpoint is None:
            raise AlarmSourceNotFoundError(external_source_id)
        return AlarmSourceView(
            external_source_id, endpoint, await self._cameras(external_source_id)
        )

    async def configure(
        self, external_source_id: str, data: AlarmSourceInput, *, actor_id: uuid.UUID | None
    ) -> AlarmSourceView:
        if not external_source_id.strip():
            raise InvalidAlarmSourceError("external_source_id must not be blank")
        if data.endpoint_type not in _SOURCE_TYPES:
            raise InvalidAlarmSourceError(f"unsupported endpoint type: {data.endpoint_type!r}")
        priority = data.priority
        if priority is None and data.endpoint_type == "panic_button":
            priority = "critical"
        if priority is not None and priority not in _PRIORITIES:
            raise InvalidAlarmSourceError(f"invalid priority: {priority!r}")

        await self._s.rollback()
        endpoint = await self._endpoint_for(external_source_id)
        created = endpoint is None
        if endpoint is None:
            endpoint = TechnicalEndpoint(
                name=data.endpoint_name,
                type=data.endpoint_type,
                provider_id=_PROVIDER_ID,
                external_source_ids=[external_source_id],
            )
            self._s.add(endpoint)
        else:
            endpoint.name = data.endpoint_name
            endpoint.type = data.endpoint_type
            endpoint.active_config_version = endpoint.active_config_version + 1
        endpoint.site = data.site
        endpoint.default_priority = priority
        endpoint.popup_profile = data.popup_profile
        endpoint.escalation_profile = data.escalation_profile
        endpoint.workflow_selection_policy = data.workflow_selection_policy
        endpoint.enabled = data.enabled
        await self._s.flush()

        await self._replace_cameras(
            external_source_id, endpoint.id, data.camera_refs, data.provider_instance_id
        )

        await AuditService(self._s).write(
            AuditAction.CODA_ALARM_SOURCE_CONFIGURED,
            actor_user_id=actor_id,
            target_type="coda_alarm_source",
            target_id=external_source_id,
            after={
                "endpoint_id": str(endpoint.id),
                "created": created,
                "type": endpoint.type,
                "priority": priority,
                "camera_count": len([r for r in data.camera_refs if r.strip()]),
                "enabled": data.enabled,
            },
        )
        await self._s.commit()
        return await self.get(external_source_id)

    async def remove(self, external_source_id: str, *, actor_id: uuid.UUID | None) -> None:
        await self._s.rollback()
        endpoint = await self._endpoint_for(external_source_id)
        if endpoint is None:
            raise AlarmSourceNotFoundError(external_source_id)
        endpoint.external_source_ids = [
            x for x in (endpoint.external_source_ids or []) if x != external_source_id
        ]
        endpoint.active_config_version = endpoint.active_config_version + 1
        await self._s.execute(
            delete(IntegrationCameraMapping).where(
                IntegrationCameraMapping.alarm_source_external_id == external_source_id
            )
        )
        await AuditService(self._s).write(
            AuditAction.CODA_ALARM_SOURCE_REMOVED,
            actor_user_id=actor_id,
            target_type="coda_alarm_source",
            target_id=external_source_id,
            after={"endpoint_id": str(endpoint.id)},
        )
        await self._s.commit()

    # --- internals --------------------------------------------------------

    async def _endpoint_for(self, external_source_id: str) -> TechnicalEndpoint | None:
        rows = (
            (
                await self._s.execute(
                    select(TechnicalEndpoint)
                    .where(TechnicalEndpoint.provider_id == _PROVIDER_ID)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        for e in rows:
            if external_source_id in (e.external_source_ids or []):
                return e
        return None

    async def _cameras(self, external_source_id: str) -> list[str]:
        rows = (
            (
                await self._s.execute(
                    select(IntegrationCameraMapping)
                    .where(IntegrationCameraMapping.alarm_source_external_id == external_source_id)
                    .order_by(IntegrationCameraMapping.ordinal, IntegrationCameraMapping.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        return [r.camera_external_ref for r in rows]

    async def _replace_cameras(
        self,
        external_source_id: str,
        endpoint_id: uuid.UUID,
        camera_refs: list[str],
        provider_instance_id: str | None,
    ) -> None:
        await self._s.execute(
            delete(IntegrationCameraMapping).where(
                IntegrationCameraMapping.alarm_source_external_id == external_source_id
            )
        )
        for ordinal, ref in enumerate(r for r in camera_refs if r.strip()):
            self._s.add(
                IntegrationCameraMapping(
                    endpoint_id=endpoint_id,
                    alarm_source_external_id=external_source_id,
                    camera_external_ref=ref,
                    ordinal=ordinal,
                    provider_instance_id=provider_instance_id,
                )
            )
        await self._s.flush()
