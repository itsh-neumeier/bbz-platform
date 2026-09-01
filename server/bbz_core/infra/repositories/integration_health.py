"""Integration-health aggregation (roadmap E22-05, MASTER_PROMPT §23 / §8.14).

A single uniform view over every **active** integration (the one configured for
its domain): its normalised state, when it was last checked / ok / failing, how
many checks in a row have failed, and when it was last observed doing work.

:meth:`IntegrationHealthService.refresh` probes each active integration's
``health()`` (bounded, in parallel) and upserts one ``integration_health`` row;
:meth:`overview` reads the rows back. The ``integration-health`` singleton runs
``refresh`` on a cadence so the table stays current for alert rules (E22-06);
``GET /api/v1/integrations/health`` also refreshes before it reads.

CUCM's own health feed is E12-15 (Epic 12, not built) — it slots in here as
another ``(domain, id)`` pair when it lands, no schema change.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.integration_health import IntegrationHealth
from bbz_core.integrations_host.providers import (
    NoActiveProvider,
    active_monitor_provider,
    active_telephony_provider,
    active_video_provider,
    active_weather_provider,
)
from bbz_core.logging import get_logger
from bbz_core.redaction import scrub
from bbz_core.settings import get_settings

_log = get_logger(__name__)

_PROBE_TIMEOUT = 5.0

#: SDK HealthState -> the normalised operator vocabulary (§8.14)
_STATE_MAP = {
    "healthy": "ok",
    "degraded": "degraded",
    "unavailable": "down",
    "disabled": "disabled",
    "unknown": "down",
}

_PROVIDER_FOR: dict[str, Callable[[], Awaitable[Any]]] = {
    "telephony": active_telephony_provider,
    "video": active_video_provider,
    "weather": active_weather_provider,
    "monitor": active_monitor_provider,
}


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


@dataclass(frozen=True)
class IntegrationHealthView:
    integration_id: str
    domain: str
    state: str
    summary: str
    checked_at: _dt.datetime | None
    last_ok_at: _dt.datetime | None
    last_error_at: _dt.datetime | None
    consecutive_errors: int
    last_activity_at: _dt.datetime | None
    details: dict[str, Any]


@dataclass(frozen=True)
class _Probe:
    domain: str
    integration_id: str
    state: str
    summary: str
    details: dict[str, Any]


class IntegrationHealthService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def _active(self) -> list[tuple[str, str]]:
        s = get_settings()
        return [
            ("telephony", s.telephony_integration_id),
            ("video", s.video_integration_id),
            ("weather", s.weather_integration_id),
            ("monitor", s.monitor_integration_id),
        ]

    async def _probe(self, domain: str, integration_id: str) -> _Probe:
        try:
            provider = await asyncio.wait_for(_PROVIDER_FOR[domain](), timeout=_PROBE_TIMEOUT)
            report = await asyncio.wait_for(provider.health(), timeout=_PROBE_TIMEOUT)
        except NoActiveProvider:
            return _Probe(domain, integration_id, "down", "no active integration", {})
        except Exception as exc:  # a probe must never raise
            return _Probe(domain, integration_id, "down", f"{type(exc).__name__}: {exc}"[:300], {})
        state = _STATE_MAP.get(str(report.state), "down")
        details = scrub({str(k): v for k, v in dict(report.details).items()})
        return _Probe(domain, integration_id, state, report.summary[:300], details)

    async def _last_activity(self, integration_id: str) -> _dt.datetime | None:
        # best-effort: the newest provider-inbox row keyed by this integration id
        return (
            await self._s.execute(
                select(func.max(ProviderEventInbox.received_at)).where(
                    ProviderEventInbox.provider == integration_id
                )
            )
        ).scalar_one_or_none()

    async def refresh(self) -> list[IntegrationHealthView]:
        await self._s.rollback()  # release any autobegun read tx
        probes = await asyncio.gather(*(self._probe(domain, iid) for domain, iid in self._active()))
        now = _now()
        async with self._s.begin():
            # plain tuples, not ORM objects — so overview()'s later select is not
            # served the pre-write rows from the identity map (expire_on_commit=False)
            prior = {
                row.integration_id: row
                for row in (
                    await self._s.execute(
                        select(
                            IntegrationHealth.integration_id,
                            IntegrationHealth.consecutive_errors,
                            IntegrationHealth.last_ok_at,
                            IntegrationHealth.last_error_at,
                        )
                    )
                ).all()
            }
            for p in probes:
                was = prior.get(p.integration_id)
                ok = p.state in ("ok", "disabled")
                consecutive = 0 if ok else ((was.consecutive_errors + 1) if was else 1)
                values = {
                    "integration_id": p.integration_id,
                    "domain": p.domain,
                    "state": p.state,
                    "summary": p.summary,
                    "checked_at": now,
                    "last_ok_at": now if ok else (was.last_ok_at if was else None),
                    "last_error_at": now if not ok else (was.last_error_at if was else None),
                    "consecutive_errors": consecutive,
                    "last_activity_at": await self._last_activity(p.integration_id),
                    "details": p.details,
                    "updated_at": now,
                }
                stmt = pg_insert(IntegrationHealth).values(**values)
                await self._s.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["integration_id"],
                        set_={k: values[k] for k in values if k != "integration_id"},
                    )
                )
        return await self.overview()

    async def overview(self) -> list[IntegrationHealthView]:
        rows = (
            await self._s.execute(
                select(IntegrationHealth).order_by(
                    IntegrationHealth.domain, IntegrationHealth.integration_id
                )
            )
        ).scalars()
        return [
            IntegrationHealthView(
                integration_id=r.integration_id,
                domain=r.domain,
                state=r.state,
                summary=r.summary,
                checked_at=r.checked_at,
                last_ok_at=r.last_ok_at,
                last_error_at=r.last_error_at,
                consecutive_errors=r.consecutive_errors,
                last_activity_at=r.last_activity_at,
                details=dict(r.details),
            )
            for r in rows
        ]
