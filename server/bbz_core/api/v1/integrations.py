"""Integration-scoped admin / diagnostics API.

- ``GET /api/v1/integrations/health`` (E22-05) — the uniform view over **every
  active** integration: normalised state, check / last-ok / last-error times,
  consecutive-error count, last observed activity. Live-probes then reads the
  ``integration_health`` table.
- ``GET /api/v1/integrations/coda_video/diagnostics`` (E16-10) — the deep,
  Coda-specific view (throughput / latency / unmapped sources / camera actions).

Both need ``integrations.diagnostics`` and carry no secrets.
"""

from __future__ import annotations

import datetime as _dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.infra.repositories.coda_diagnostics import CodaDiagnosticsService
from bbz_core.infra.repositories.integration_health import IntegrationHealthService
from bbz_core.integrations_host.providers import NoActiveProvider, active_video_provider

router = APIRouter(prefix="/integrations", tags=["integrations"])


class IntegrationHealthOut(BaseModel):
    integration_id: str
    domain: str
    state: str  # ok | degraded | down | disabled
    summary: str
    checked_at: _dt.datetime | None
    last_ok_at: _dt.datetime | None
    last_error_at: _dt.datetime | None
    consecutive_errors: int
    last_activity_at: _dt.datetime | None
    details: dict[str, object]


class IntegrationHealthOverview(BaseModel):
    integrations: list[IntegrationHealthOut]


@router.get("/health", response_model=IntegrationHealthOverview)
async def integration_health(
    _: AuthContext = Depends(require("integrations.diagnostics")),
    session: AsyncSession = Depends(db_session),
) -> IntegrationHealthOverview:
    """Live health of every active integration (E22-05). Probes each provider,
    persists the result to ``integration_health`` and returns the table. The
    ``integration-health`` singleton keeps it current between calls."""
    views = await IntegrationHealthService(session).refresh()
    return IntegrationHealthOverview(integrations=[IntegrationHealthOut(**vars(v)) for v in views])


class HealthOut(BaseModel):
    state: str
    summary: str
    details: dict[str, str | int | float | bool | None]


class CodaDiagnosticsOut(BaseModel):
    integration_id: str = "coda_video"
    health: HealthOut
    capabilities: list[str]
    events_total: int
    signals_total: int
    last_event_at: _dt.datetime | None
    last_event_processing_ms: int | None
    unmapped_total: int
    last_camera_action_at: _dt.datetime | None
    camera_actions_failed: int
    camera_actions_pending: int


@router.get("/coda_video/diagnostics", response_model=CodaDiagnosticsOut)
async def coda_video_diagnostics(
    _: AuthContext = Depends(require("integrations.diagnostics")),
    session: AsyncSession = Depends(db_session),
) -> CodaDiagnosticsOut:
    session_agg = CodaDiagnosticsService(session)
    agg = await session_agg.collect()

    try:
        provider = await active_video_provider()
        report = await provider.health()
        health = HealthOut(
            state=str(report.state),
            summary=report.summary,
            details=dict(report.details),
        )
        capabilities = sorted(str(c) for c in provider.capabilities())
    except NoActiveProvider:
        # diagnostics must still work when the integration is down
        health = HealthOut(
            state="unavailable", summary="no active coda_video integration", details={}
        )
        capabilities = []

    return CodaDiagnosticsOut(
        health=health,
        capabilities=capabilities,
        events_total=agg.events_total,
        signals_total=agg.signals_total,
        last_event_at=agg.last_event_at,
        last_event_processing_ms=agg.last_event_processing_ms,
        unmapped_total=agg.unmapped_total,
        last_camera_action_at=agg.last_camera_action_at,
        camera_actions_failed=agg.camera_actions_failed,
        camera_actions_pending=agg.camera_actions_pending,
    )
