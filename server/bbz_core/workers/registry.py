"""The named cluster-wide singletons every node starts (roadmap E06-06).

Each singleton runs on **every** node but does work only on the node that
currently holds its etcd lease (ADR-0018) — so background work never runs
twice. ``/cluster/status.leaders`` shows the holder per name; a failover moves
it within ``2 * ttl`` (``run_as_singleton`` steps down the instant a lease
renewal fails and the new leader campaigns on the next cycle).

``do_work`` is one **tick**, not a loop: :func:`run_as_singleton` calls it once
per cycle while leader.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

#: leader-election names, also the keys under ``/bbz/leader/`` in etcd.
SINGLETON_NAMES: tuple[str, ...] = (
    "outbox-dispatcher",
    "workflow-timer",
    "trigger-engine",
    "weather-refresh",
    "directory-sync",
    "integration-health",
    "audit-chain",
    "telephony-events",
)


@dataclass(frozen=True)
class Singleton:
    name: str
    tick: Callable[[], Awaitable[object]]


async def _outbox_tick() -> object:
    from bbz_core.workers.camera_handlers import CAMERA_HANDLERS
    from bbz_core.workers.outbox_dispatcher import DEFAULT_HANDLERS, OutboxDispatcher

    return await OutboxDispatcher({**DEFAULT_HANDLERS, **CAMERA_HANDLERS}).run_once()


async def _workflow_timer_tick() -> object:
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.repositories.workflow_engine import WorkflowEngineService

    async with session_scope() as session:
        return await WorkflowEngineService(session).fire_due_timers()


async def _trigger_engine_tick() -> object:
    """Drain the provider inbox: run every unprocessed inbound signal through the
    trigger engine, exactly once (E15-15 / ADR-0024)."""
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.repositories.trigger_engine import TriggerEngine

    async with session_scope() as session:
        results = await TriggerEngine(session).resume_unprocessed()
        return len(results)


async def _weather_refresh_tick() -> object:
    """Poll the active weather integration and refresh the DWD snapshot / health
    (E18-06). Returns the number of items ingested; safe on an unconfigured
    system (returns 0)."""
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.repositories.weather_refresh import WeatherRefreshService

    async with session_scope() as session:
        return await WeatherRefreshService(session).refresh()


async def _directory_sync_tick() -> object:
    """Reconcile BBZ users/roles against the directory (E21-04) — but only once
    per ``ldap_sync_interval_seconds``. Returns the number of changes applied
    (created + deactivated + role reconciles). Safe on an unconfigured system
    (returns 0)."""
    import datetime as _dt

    from sqlalchemy import select

    from bbz_core.infra.db import session_scope
    from bbz_core.infra.models.directory_sync import DirectorySyncState
    from bbz_core.infra.repositories.directory_sync import DirectorySyncService
    from bbz_core.settings import get_settings

    settings = get_settings()
    if not settings.ldap_sync_enabled or not settings.ldap_url:
        return 0

    async with session_scope() as session:
        last = (
            await session.execute(
                select(DirectorySyncState.last_run_at).where(DirectorySyncState.source == "ldap_ad")
            )
        ).scalar_one_or_none()
        if last is not None:
            age = (_dt.datetime.now(_dt.UTC) - last).total_seconds()
            if age < settings.ldap_sync_interval_seconds:
                return 0
        report = await DirectorySyncService(session).run()
        return report.created + report.deactivated + report.role_reconciles


async def _integration_health_tick() -> object:
    """Refresh the ``integration_health`` table (E22-05) — but only once per
    ``integration_health_interval_seconds``. Returns the number of integrations
    probed. Always safe (the active integrations always resolve to a provider or
    a ``down`` row)."""
    import datetime as _dt

    from sqlalchemy import func, select

    from bbz_core.infra.db import session_scope
    from bbz_core.infra.models.integration_health import IntegrationHealth
    from bbz_core.infra.repositories.integration_health import IntegrationHealthService
    from bbz_core.settings import get_settings

    async with session_scope() as session:
        last = (
            await session.execute(select(func.max(IntegrationHealth.checked_at)))
        ).scalar_one_or_none()
        if last is not None:
            age = (_dt.datetime.now(_dt.UTC) - last).total_seconds()
            if age < get_settings().integration_health_interval_seconds:
                return 0
        return len(await IntegrationHealthService(session).refresh())


async def _audit_chain_tick() -> object:
    """Seal new ``audit_events`` rows into the hash chain and re-verify it
    (E23-09) — once per ``audit_chain_interval_seconds``. A verification failure
    audits ``AUDIT_INTEGRITY_ALERT`` and logs an error. Returns the number of
    rows sealed this tick; a no-op when the chain is disabled."""
    import datetime as _dt

    from sqlalchemy import func, select

    from bbz_core.audit import AuditAction, AuditService
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.models.audit import AuditChainLink
    from bbz_core.infra.repositories.audit_chain import AuditChainService
    from bbz_core.logging import get_logger
    from bbz_core.settings import get_settings

    if not get_settings().audit_hash_chain_enabled:
        return 0

    async with session_scope() as session:
        last = (
            await session.execute(select(func.max(AuditChainLink.sealed_at)))
        ).scalar_one_or_none()
        if last is not None:
            age = (_dt.datetime.now(_dt.UTC) - last).total_seconds()
            if age < get_settings().audit_chain_interval_seconds:
                return 0

        sealed = (await AuditChainService(session).seal()).sealed
        result = await AuditChainService(session).verify()
        if not result.ok:
            get_logger(__name__).error(
                "audit_integrity_alert", first_bad_seq=result.first_bad_seq, detail=result.detail
            )
            await session.rollback()  # verify() left a read transaction open
            async with session.begin():
                await AuditService(session).write(
                    AuditAction.AUDIT_INTEGRITY_ALERT,
                    target_type="audit_chain",
                    target_id=str(result.first_bad_seq),
                    after={"first_bad_seq": result.first_bad_seq, "detail": result.detail},
                )
        return sealed


async def _telephony_events_tick() -> object:
    """Drain the active telephony provider's buffered call events and feed each
    through ``ingest_telephony_event`` (validate → provider inbox → dedupe →
    call aggregate → trigger signal, E11-03).

    This is the pump E11-05 never wired: no background task consumes a telephony
    provider's stream today. The **mock** provider is skipped — its events are
    drained on demand by the test endpoints (``/telephony/_mock/...``,
    ``calls.py::_control``) for deterministic E2E. A real provider (``telephony_sip``,
    later ``telephony_cucm``) exposes ``drain_events`` and is drained here.
    Returns the number of events ingested; a no-op when there is no provider or
    it has nothing buffered.
    """
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.telephony_ingest import (
        TelephonyEventRejected,
        ingest_telephony_event,
    )
    from bbz_core.integrations_host.providers import NoActiveProvider, active_telephony_provider

    try:
        provider = await active_telephony_provider()
    except NoActiveProvider:
        return 0
    if getattr(provider.info(), "mock", False):
        return 0
    drain = getattr(provider, "drain_events", None)
    if not callable(drain):
        return 0

    events = await drain()
    if not events:
        return 0
    ingested = 0
    async with session_scope() as session:
        for ev in events:
            raw = ev.model_dump(mode="json")
            try:
                async with session.begin():
                    result = await ingest_telephony_event(session, raw)
                if result.outcome.value == "new":
                    ingested += 1
            except TelephonyEventRejected:
                continue  # a malformed provider event must not stall the pump
    return ingested


def cluster_singletons() -> list[Singleton]:
    return [
        Singleton("outbox-dispatcher", _outbox_tick),
        Singleton("workflow-timer", _workflow_timer_tick),
        Singleton("trigger-engine", _trigger_engine_tick),
        Singleton("weather-refresh", _weather_refresh_tick),
        Singleton("directory-sync", _directory_sync_tick),
        Singleton("integration-health", _integration_health_tick),
        Singleton("audit-chain", _audit_chain_tick),
        Singleton("telephony-events", _telephony_events_tick),
    ]
