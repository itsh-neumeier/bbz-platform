"""Cluster status endpoint (MASTER_PROMPT §4/§23, roadmap E06-04).

Returns the **live** HA state — DCS health + quorum, the app leader holders,
each node's PostgreSQL role and replication lag, the highest applied
``event_seq``. Gathering lives in :mod:`bbz_core.infra.cluster_status`, which
degrades honestly: an unreachable etcd yields ``dcs_healthy: false`` /
``quorum: null`` rather than a 500. ``system.cluster.view`` is required — the
client agent uses this for server selection.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.infra.cluster_status import gather_status

router = APIRouter(prefix="/cluster", tags=["cluster"])


class NodeStatus(BaseModel):
    node_id: str
    app_state: str
    db_role: str
    replication_lag_bytes: int | None = None


class ClusterStatus(BaseModel):
    stub: bool = False
    dcs: str
    dcs_healthy: bool | None = None
    quorum: bool | None = None
    control_leader: str | None = None
    leaders: dict[str, str] = Field(
        default_factory=dict, description="etcd /bbz/leader/<name> -> node_id holding it"
    )
    singletons: list[str] = Field(
        default_factory=list, description="cluster singletons to look up in `leaders`"
    )
    nodes: list[NodeStatus]
    last_event_seq: int | None = Field(
        default=None, description="Highest applied global event sequence."
    )


@router.get("/status", response_model=ClusterStatus)
async def status(
    _: AuthContext = Depends(require("system.cluster.view")),
    session: AsyncSession = Depends(db_session),
) -> ClusterStatus:
    return ClusterStatus.model_validate(await gather_status(session))
