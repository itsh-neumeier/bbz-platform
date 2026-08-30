"""System endpoints that require a permission (also the ``require()`` demo)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.audit import AuditAction, AuditService
from bbz_core.settings import get_settings

router = APIRouter(prefix="/system", tags=["system"])


class SystemInfo(BaseModel):
    node_id: str
    environment: str


@router.get("/info", response_model=SystemInfo)
async def system_info(
    _: AuthContext = Depends(require("system.cluster.view")),
) -> SystemInfo:
    s = get_settings()
    return SystemInfo(node_id=s.node_id, environment=s.environment)


class RollingUpdateMarkerIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: Literal["started", "completed"]
    image: str = Field(min_length=1, max_length=300)
    notes: str | None = Field(default=None, max_length=1000)


_ACTION = {
    "started": AuditAction.ROLLING_UPDATE_STARTED,
    "completed": AuditAction.ROLLING_UPDATE_COMPLETED,
}


@router.post("/rolling-update", status_code=status.HTTP_202_ACCEPTED)
async def rolling_update_marker(
    body: RollingUpdateMarkerIn,
    ctx: AuthContext = Depends(require("system.cluster.manage")),
    session: AsyncSession = Depends(db_session),
) -> dict[str, str]:
    """Record a maintenance-window marker on the audit trail. Called by
    ``tools/rolling-update.sh`` at the start and end of a rolling update
    (roadmap E06-09)."""
    await session.rollback()  # release the autobegun require() read tx
    async with session.begin():
        await AuditService(session).write(
            _ACTION[body.phase],
            actor_user_id=ctx.user_id,
            target_type="cluster",
            target_id=get_settings().node_id,
            after={"phase": body.phase, "image": body.image},
            reason=body.notes,
        )
    return {"phase": body.phase, "image": body.image}
