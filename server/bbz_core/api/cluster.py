"""Cluster status endpoint (MASTER_PROMPT §4/§23).

Phase 0 returns a **static, honestly-labelled stub**. Real values (Patroni role,
replication lag, DCS quorum, CONTROL_LEADER holder) are wired in Phase 2
(ADR-0001 / ADR-0018). The shape is fixed now so the client agent and the web
cluster view can be built against it.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from bbz_core.settings import get_settings

router = APIRouter(prefix="/cluster", tags=["cluster"])


class NodeStatus(BaseModel):
    node_id: str
    app_state: Literal["active", "starting", "draining", "down", "unknown"]
    db_role: Literal["primary", "standby", "unknown"]
    replication_lag_bytes: int | None = None


class ClusterStatus(BaseModel):
    stub: bool = Field(
        default=True,
        description="True until Phase 2 wires Patroni/DCS. Do not treat as authoritative.",
    )
    dcs: str
    dcs_healthy: bool | None = None
    quorum: bool | None = None
    control_leader: str | None = None
    nodes: list[NodeStatus]
    last_event_seq: int | None = Field(
        default=None, description="Highest applied global event sequence (Phase 1)."
    )


@router.get("/status", response_model=ClusterStatus)
async def status() -> ClusterStatus:
    s = get_settings()
    return ClusterStatus(
        dcs=s.cluster_dcs,
        nodes=[
            NodeStatus(node_id=s.node_id, app_state="active", db_role="unknown"),
        ],
    )
