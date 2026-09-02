"""Prometheus metrics (roadmap E06-13 + E22-02, MASTER_PROMPT §23).

E06-13 landed the HA / cluster gauges; E22-02 completes the §23 set: request
latency, DB pool state, connected clients, call-line status, pending commands and
integration health. All series are **per node** — scrape each node and compare.

Two feeds:
- **live** — counters the request path / stream handlers update as they go
  (``HTTP_REQUEST_DURATION``, ``STREAM_CONNECTIONS``);
- **on scrape** — gauges :func:`render` refreshes from
  :func:`bbz_core.infra.cluster_status.gather_status`, a few DB reads, the engine
  pool and each loaded integration's ``health()``.

Exposed at ``GET /api/v1/system/metrics`` behind ``system.cluster.view`` — not a
public endpoint (a dedicated internal scrape port is E22-07). Labels are kept
low-cardinality on purpose: the request histogram uses the **route template**
(``/api/v1/events/{event_id}``), never the raw path.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.cluster_status import gather_status
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.settings import get_settings

REGISTRY = CollectorRegistry()

# --- live: the request path updates these -------------------------------
HTTP_REQUEST_DURATION = Histogram(
    "bbz_http_request_duration_seconds",
    "HTTP request latency by method, route template and status",
    ["method", "route", "status"],
    registry=REGISTRY,
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)
STREAM_CONNECTIONS = Gauge(
    "bbz_stream_connections",
    "Open event-stream connections on this node",
    ["transport"],
    registry=REGISTRY,
)

# --- on scrape: HA / cluster (E06-13) ----------------------------------
_DCS_HEALTHY = Gauge("bbz_cluster_dcs_healthy", "etcd reachable (1/0)", registry=REGISTRY)
_QUORUM = Gauge("bbz_cluster_quorum", "etcd raft quorum present (1/0)", registry=REGISTRY)
_NODE_PRIMARY = Gauge(
    "bbz_cluster_node_is_primary",
    "node holds the PostgreSQL primary (1/0)",
    ["node"],
    registry=REGISTRY,
)
_REPL_LAG = Gauge(
    "bbz_replication_lag_bytes", "standby replication lag", ["node"], registry=REGISTRY
)
_EVENT_HEAD = Gauge(
    "bbz_event_seq_head", "highest applied domain_events.event_seq on this node", registry=REGISTRY
)
_OUTBOX_PENDING = Gauge(
    "bbz_outbox_pending", "external_action_outbox rows awaiting dispatch", registry=REGISTRY
)
_LEADER = Gauge(
    "bbz_worker_leader",
    "this node holds the singleton's etcd lease (1/0)",
    ["singleton"],
    registry=REGISTRY,
)

# --- on scrape: app / §23 (E22-02) ------------------------------------
_DB_POOL = Gauge(
    "bbz_db_pool_connections",
    "SQLAlchemy async engine pool connections on this node",
    ["state"],  # in_use | idle | overflow
    registry=REGISTRY,
)
_CONNECTED_CLIENTS = Gauge(
    "bbz_connected_clients",
    "active sessions (not revoked, not expired) — one per logged-in client",
    registry=REGISTRY,
)
_COMMANDS_PENDING = Gauge(
    "bbz_commands_pending",
    "accepted commands with no result yet (a client that submitted offline and "
    "has not synced the outcome)",
    registry=REGISTRY,
)
_CALL_LINES = Gauge("bbz_call_lines", "telephony lines by state", ["state"], registry=REGISTRY)
_CALLS_ACTIVE = Gauge("bbz_calls_active", "calls not in a terminal state", registry=REGISTRY)
_RESTORE_TEST_AGE = Gauge(
    "bbz_restore_test_age_seconds",
    "seconds since the last automated restore test (E24-05); +Inf if none ever ran",
    registry=REGISTRY,
)
_RESTORE_TEST_OK = Gauge(
    "bbz_restore_test_ok", "last automated restore test passed (1/0)", registry=REGISTRY
)
_INTEGRATION_HEALTH = Gauge(
    "bbz_integration_health",
    "loaded integration health: 1 healthy / 0.5 degraded / 0 unavailable|unknown / -1 disabled",
    ["domain", "integration"],
    registry=REGISTRY,
)

_HEALTH_VALUE = {
    "healthy": 1.0,
    "degraded": 0.5,
    "unavailable": 0.0,
    "unknown": 0.0,
    "disabled": -1.0,
}
_CALL_TERMINAL = ("disconnected", "failed")


def stream_connection(transport: str) -> Any:
    """Context manager: ``with stream_connection("sse"): ...`` around a stream."""
    return STREAM_CONNECTIONS.labels(transport=transport).track_inprogress()


def observe_request(method: str, route: str, status: int, duration_seconds: float) -> None:
    """Record one finished HTTP request (called by the metrics middleware)."""
    HTTP_REQUEST_DURATION.labels(method=method, route=route, status=str(status)).observe(
        duration_seconds
    )


def _pool_stat(pool: Any, name: str) -> int:
    fn = getattr(pool, name, None)
    try:
        return int(fn()) if callable(fn) else 0
    except Exception:
        return 0


async def render(session: AsyncSession) -> tuple[bytes, str]:
    await _refresh_cluster(session)
    await _refresh_app(session)
    await _refresh_integrations()
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


async def _refresh_cluster(session: AsyncSession) -> None:
    s = get_settings()
    try:
        status = await gather_status(session)
    except Exception:
        status = {}

    _DCS_HEALTHY.set(1 if status.get("dcs_healthy") else 0)
    _QUORUM.set(1 if status.get("quorum") else 0)
    for node in status.get("nodes", []):
        _NODE_PRIMARY.labels(node=node["node_id"]).set(1 if node.get("db_role") == "primary" else 0)
        if node.get("replication_lag_bytes") is not None:
            _REPL_LAG.labels(node=node["node_id"]).set(node["replication_lag_bytes"])
    if status.get("last_event_seq") is not None:
        _EVENT_HEAD.set(status["last_event_seq"])
    leaders = status.get("leaders", {})
    for name in status.get("singletons", []):
        _LEADER.labels(singleton=name).set(1 if leaders.get(name) == s.node_id else 0)

    try:
        pending = (
            await session.execute(
                select(func.count())
                .select_from(ExternalActionOutbox)
                .where(ExternalActionOutbox.status == "pending")
            )
        ).scalar_one()
        _OUTBOX_PENDING.set(pending)
    except Exception:
        pass


async def _refresh_app(session: AsyncSession) -> None:
    from bbz_core.infra.db import get_engine
    from bbz_core.infra.models.commands import Command
    from bbz_core.infra.models.session import Session as SessionRow
    from bbz_core.infra.models.telephony import Call, Line

    pool: Any = get_engine().pool
    # QueuePool exposes these; NullPool (some deploys) does not — degrade to 0.
    _DB_POOL.labels(state="in_use").set(_pool_stat(pool, "checkedout"))
    _DB_POOL.labels(state="idle").set(_pool_stat(pool, "checkedin"))
    _DB_POOL.labels(state="overflow").set(max(_pool_stat(pool, "overflow"), 0))

    try:
        clients = (
            await session.execute(
                select(func.count())
                .select_from(SessionRow)
                .where(SessionRow.revoked_at.is_(None), SessionRow.expires_at > func.now())
            )
        ).scalar_one()
        _CONNECTED_CLIENTS.set(clients)

        commands = (
            await session.execute(
                select(func.count()).select_from(Command).where(Command.result_status.is_(None))
            )
        ).scalar_one()
        _COMMANDS_PENDING.set(commands)

        by_state = (
            await session.execute(select(Line.state, func.count()).group_by(Line.state))
        ).all()
        seen = {row[0] for row in by_state}
        for line_state, count in by_state:
            _CALL_LINES.labels(state=line_state).set(count)
        for line_state in ("in_service", "out_of_service", "unknown"):
            if line_state not in seen:
                _CALL_LINES.labels(state=line_state).set(0)

        active_calls = (
            await session.execute(
                select(func.count()).select_from(Call).where(Call.state.notin_(_CALL_TERMINAL))
            )
        ).scalar_one()
        _CALLS_ACTIVE.set(active_calls)

        await _refresh_restore_test(session)
    except Exception:
        pass


async def _refresh_restore_test(session: AsyncSession) -> None:
    from bbz_core.infra.models.audit import AuditEvent

    row = (
        await session.execute(
            select(AuditEvent.occurred_at_utc, AuditEvent.after)
            .where(AuditEvent.action == "RESTORE_TEST_COMPLETED")
            .order_by(AuditEvent.occurred_at_utc.desc())
            .limit(1)
        )
    ).first()
    if row is None:
        _RESTORE_TEST_AGE.set(float("inf"))
        _RESTORE_TEST_OK.set(0)
        return
    occurred, after = row
    age = (_dt.datetime.now(_dt.UTC) - occurred).total_seconds()
    _RESTORE_TEST_AGE.set(max(age, 0.0))
    _RESTORE_TEST_OK.set(1 if (after or {}).get("ok") else 0)


async def _refresh_integrations() -> None:
    from bbz_core.integrations_host.providers import loaded_providers

    async def _one(key: str, provider: Any) -> None:
        domain, _, integration = key.partition(":")
        try:
            report = await asyncio.wait_for(provider.health(), timeout=2.0)
            value = _HEALTH_VALUE.get(str(report.state), 0.0)
        except Exception:
            value = 0.0
        _INTEGRATION_HEALTH.labels(domain=domain, integration=integration).set(value)

    await asyncio.gather(*(_one(k, p) for k, p in loaded_providers().items()))
