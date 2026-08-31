"""Coda-integration diagnostics aggregation (roadmap E16-10).

DB-side counters for ``GET /api/v1/integrations/coda_video/diagnostics``: how many
alarm events and inbound signals have been seen, the latest one and how long it
took to process, the unmapped-source total, and the state of the camera outbox
actions. The provider's own health / capabilities are added by the API layer.
No secrets are ever read into the response (``.ai/INTEGRATIONS_CODA_VIDEO.md``).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.unmapped_signals import UnmappedSignal

_PROVIDER = "coda_video"
_CAMERA_ACTIONS = ("open_camera", "open_camera_group")


@dataclass(frozen=True)
class CodaDiagnostics:
    events_total: int
    signals_total: int
    last_event_at: _dt.datetime | None
    last_event_processing_ms: int | None
    unmapped_total: int
    last_camera_action_at: _dt.datetime | None
    camera_actions_failed: int
    camera_actions_pending: int


class CodaDiagnosticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def collect(self) -> CodaDiagnostics:
        await self._s.rollback()

        #: the immutable alarm-event rows (not the queued ``signal:`` rows)
        is_alarm_event = (ProviderEventInbox.provider == _PROVIDER) & (
            ~ProviderEventInbox.dedupe_key.like("signal:%")
        )
        events_total = (
            await self._s.execute(
                select(func.count()).select_from(ProviderEventInbox).where(is_alarm_event)
            )
        ).scalar_one()

        newest = (
            await self._s.execute(
                select(ProviderEventInbox)
                .where(is_alarm_event)
                .order_by(ProviderEventInbox.received_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        last_event_at = newest.received_at if newest else None
        last_ms: int | None = None
        if newest is not None and newest.processed_at is not None:
            delta = newest.processed_at - newest.received_at
            last_ms = max(0, int(delta.total_seconds() * 1000))

        signals_total = (
            await self._s.execute(
                select(func.count())
                .select_from(ProviderEventInbox)
                .where(ProviderEventInbox.dedupe_key.like(f"signal:{_PROVIDER}:%"))
            )
        ).scalar_one()

        unmapped_total = (
            await self._s.execute(
                select(func.coalesce(func.sum(UnmappedSignal.occurrences), 0)).where(
                    UnmappedSignal.provider == _PROVIDER
                )
            )
        ).scalar_one()

        last_camera_action_at = (
            await self._s.execute(
                select(ExternalActionOutbox.dispatched_at)
                .where(
                    ExternalActionOutbox.action_type.in_(_CAMERA_ACTIONS),
                    ExternalActionOutbox.status == "dispatched",
                )
                .order_by(ExternalActionOutbox.dispatched_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        return CodaDiagnostics(
            events_total=events_total,
            signals_total=signals_total,
            last_event_at=last_event_at,
            last_event_processing_ms=last_ms,
            unmapped_total=int(unmapped_total),
            last_camera_action_at=last_camera_action_at,
            camera_actions_failed=await self._camera_count("failed"),
            camera_actions_pending=await self._camera_count("pending"),
        )

    async def _camera_count(self, status: str) -> int:
        return (
            await self._s.execute(
                select(func.count())
                .select_from(ExternalActionOutbox)
                .where(
                    ExternalActionOutbox.action_type.in_(_CAMERA_ACTIONS),
                    ExternalActionOutbox.status == status,
                )
            )
        ).scalar_one()
