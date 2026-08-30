"""Health endpoints (MASTER_PROMPT §23).

- ``/health/live``    process is up
- ``/health/ready``   dependencies reachable AND HA state valid -> route traffic
- ``/health/details`` structured breakdown for operators/diagnostics

The client agent (and any load balancer) polls ``/health/live`` and
``/health/ready`` for failover (MASTER_PROMPT §4). Readiness is conservative and
checked **in order**, each with a ~2 s timeout:

1. **database** — the node can reach its PostgreSQL.
2. **cluster** — this node's Patroni role is known and it is *not* mid
   rejoin / replay (E06-05). Delegates to the local Patroni ``/readiness``;
   skipped when no local Patroni is configured (single-node dev).

Any failing check -> ``503 not_ready`` so the node is taken out of rotation.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from bbz_core import __version__
from bbz_core.infra.cluster_status import local_node_ready
from bbz_core.infra.db import check_database
from bbz_core.settings import get_settings

router = APIRouter(prefix="/health", tags=["health"])


class LiveResponse(BaseModel):
    status: Literal["live"] = "live"
    service: str
    version: str


class Check(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: list[Check]


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    s = get_settings()
    return LiveResponse(service=s.service_name, version=__version__)


async def _collect_checks() -> list[Check]:
    db_ok, db_detail = await check_database()
    checks = [Check(name="database", ok=db_ok, detail=db_detail)]
    cluster_ok, cluster_detail = await local_node_ready()
    checks.append(Check(name="cluster", ok=cluster_ok, detail=cluster_detail))
    return checks


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    checks = await _collect_checks()
    all_ok = all(c.ok for c in checks)
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="ready" if all_ok else "not_ready", checks=checks)


class DetailsResponse(BaseModel):
    service: str
    version: str
    environment: str
    node_id: str
    checks: list[Check]


@router.get("/details", response_model=DetailsResponse)
async def details() -> DetailsResponse:
    s = get_settings()
    return DetailsResponse(
        service=s.service_name,
        version=__version__,
        environment=s.environment,
        node_id=s.node_id,
        checks=await _collect_checks(),
    )
