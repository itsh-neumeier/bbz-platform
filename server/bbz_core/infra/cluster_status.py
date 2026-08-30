"""Real cluster-status probe (roadmap E06-04, MASTER_PROMPT §4/§23).

Gathers the live HA state from three sources and degrades honestly — a probe
that cannot reach its target yields ``null`` / ``false`` for that part, never a
500:

* **etcd** — per-endpoint ``/v3/maintenance/status`` for DCS health + whether a
  raft leader is visible (quorum), and a range read of the app leader prefix
  for the leader holders.
* **Patroni REST** — ``/cluster`` for the per-node PostgreSQL role and
  replication lag.
* **local PostgreSQL** — ``pg_is_in_recovery()`` and the receive/replay LSN
  gap, as a fallback when Patroni is unreachable and to confirm this node.

No secrets or internal endpoints go into the result.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)
_TIMEOUT = 2.0


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _unb64(s: str) -> str:
    return base64.b64decode(s.encode()).decode(errors="replace")


def _etcd_client() -> httpx.AsyncClient:
    s = get_settings()
    verify: bool | str = s.cluster_dcs_tls_ca_file or True
    cert = (
        (s.cluster_dcs_tls_cert_file, s.cluster_dcs_tls_key_file)
        if s.cluster_dcs_tls_cert_file and s.cluster_dcs_tls_key_file
        else None
    )
    return httpx.AsyncClient(timeout=_TIMEOUT, verify=verify, cert=cert)


async def _probe_etcd() -> dict[str, Any]:
    s = get_settings()
    endpoints = [e.rstrip("/") for e in s.cluster_dcs_endpoints]
    result: dict[str, Any] = {"healthy": False, "quorum": None, "leaders": {}}
    if not endpoints:
        return result

    healthy = 0
    leader_seen = False
    async with _etcd_client() as client:
        for ep in endpoints:
            try:
                r = await client.post(f"{ep}/v3/maintenance/status", json={})
                r.raise_for_status()
                data = r.json()
            except (httpx.HTTPError, ValueError):
                continue
            healthy += 1
            if data.get("leader") not in (None, "0", 0) and not data.get("errors"):
                leader_seen = True

        if healthy:
            result["healthy"] = True
            result["quorum"] = leader_seen
            result["leaders"] = await _read_leaders(client, endpoints[0])
    return result


async def _read_leaders(client: httpx.AsyncClient, endpoint: str) -> dict[str, str]:
    prefix = get_settings().worker_leader_prefix.rstrip("/") + "/"
    range_end = prefix[:-1] + chr(ord(prefix[-1]) + 1)
    try:
        r = await client.post(
            f"{endpoint}/v3/kv/range",
            json={"key": _b64(prefix), "range_end": _b64(range_end)},
        )
        r.raise_for_status()
        kvs = r.json().get("kvs", [])
    except (httpx.HTTPError, ValueError):
        return {}
    out: dict[str, str] = {}
    for kv in kvs:
        name = _unb64(kv["key"]).removeprefix(prefix)
        out[name] = _unb64(kv["value"])
    return out


async def _probe_patroni() -> dict[str, Any]:
    endpoints = [e.rstrip("/") for e in get_settings().patroni_rest_endpoints]
    if not endpoints:
        return {"reachable": False, "members": []}
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for ep in endpoints:
            try:
                r = await client.get(f"{ep}/cluster")
                r.raise_for_status()
                members = r.json().get("members", [])
            except (httpx.HTTPError, ValueError):
                continue
            return {"reachable": True, "members": [_member(m) for m in members]}
    return {"reachable": False, "members": []}


def _member(m: dict[str, Any]) -> dict[str, Any]:
    role = m.get("role", "")
    db_role = "primary" if role in ("leader", "master") else "standby" if role else "unknown"
    state = m.get("state", "")
    app_state = "active" if state in ("running", "streaming") else "unknown"
    return {
        "node_id": m.get("name", "?"),
        "db_role": db_role,
        "app_state": app_state,
        "replication_lag_bytes": m.get("lag") if isinstance(m.get("lag"), int) else None,
    }


async def _probe_local_db(session: AsyncSession) -> dict[str, Any]:
    try:
        in_recovery = (await session.execute(text("SELECT pg_is_in_recovery()"))).scalar_one()
        if in_recovery:
            lag = (
                await session.execute(
                    text(
                        "SELECT (pg_wal_lsn_diff("
                        "pg_last_wal_receive_lsn(), pg_last_wal_replay_lsn()))::bigint"
                    )
                )
            ).scalar_one()
            return {"db_role": "standby", "replication_lag_bytes": int(lag) if lag else 0}
        return {"db_role": "primary", "replication_lag_bytes": None}
    except Exception as exc:
        _log.warning("cluster_status_local_db_failed", error=str(exc))
        return {"db_role": "unknown", "replication_lag_bytes": None}


async def _last_event_seq(session: AsyncSession) -> int | None:
    try:
        seq = (await session.execute(select(func.max(DomainEvent.event_seq)))).scalar_one_or_none()
        return int(seq) if seq is not None else None
    except Exception:
        return None


async def gather_status(session: AsyncSession) -> dict[str, Any]:
    s = get_settings()
    etcd = await _probe_etcd()
    patroni = await _probe_patroni()
    local = await _probe_local_db(session)

    nodes = list(patroni["members"])
    if not any(n["node_id"] == s.node_id for n in nodes):
        nodes.append(
            {
                "node_id": s.node_id,
                "db_role": local["db_role"],
                "app_state": "active",
                "replication_lag_bytes": local["replication_lag_bytes"],
            }
        )

    leaders = etcd["leaders"]
    return {
        "stub": False,
        "dcs": s.cluster_dcs,
        "dcs_healthy": etcd["healthy"],
        "quorum": etcd["quorum"],
        "control_leader": leaders.get("control_leader"),
        "leaders": leaders,
        "nodes": nodes,
        "last_event_seq": await _last_event_seq(session),
    }
