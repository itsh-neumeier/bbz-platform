"""System endpoints that require a permission (also the ``require()`` demo)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext
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
