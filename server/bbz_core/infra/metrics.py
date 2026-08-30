"""HA / cluster Prometheus metrics (roadmap E06-13, MASTER_PROMPT §23).

A **minimal, HA-relevant** metric set — full observability is Epic 22. The
gauges that need a live process counter (stream connections) are incremented
by the SSE / WebSocket handlers; the rest are refreshed on scrape from
:func:`bbz_core.infra.cluster_status.gather_status` plus a couple of DB reads.

Exposed at ``GET /api/v1/system/metrics`` behind ``system.cluster.view`` — not
a public endpoint. A dedicated internal scrape port is Epic 22.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.cluster_status import gather_status
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.settings import get_settings

REGISTRY = CollectorRegistry()

# --- live process counters (handlers inc/dec these) -----------------------
STREAM_CONNECTIONS = Gauge(
    "bbz_stream_connections",
    "Open event-stream connections on this node",
    ["transport"],
    registry=REGISTRY,
)

# --- refreshed on scrape -------------------------------------------------
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


def stream_connection(transport: str) -> Any:
    """Context manager: ``with stream_connection("sse"): ...`` around a stream."""
    return STREAM_CONNECTIONS.labels(transport=transport).track_inprogress()


async def render(session: AsyncSession) -> tuple[bytes, str]:
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

    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
