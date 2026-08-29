"""Audit read API (E02-12 minimal; E04-04 is the full version)."""

from __future__ import annotations

import datetime as _dt
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.audit.writer import AuditWriter

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    id: uuid.UUID
    occurred_at_utc: _dt.datetime
    node_id: str
    action: str
    actor_user_id: uuid.UUID | None
    actor_client_id: str | None
    workplace_id: str | None
    target_type: str | None
    target_id: str | None
    reason: str | None
    correlation_id: str | None


@router.get("", response_model=list[AuditEventOut])
async def list_audit(
    action: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    since: _dt.datetime | None = None,
    until: _dt.datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthContext = Depends(require("system.audit.view")),
    session: AsyncSession = Depends(db_session),
) -> list[AuditEventOut]:
    rows = await AuditWriter(session).query(
        action=action,
        actor_user_id=actor_user_id,
        target_type=target_type,
        since=since,
        until=until,
        limit=limit,
    )
    return [AuditEventOut(**r.__dict__) for r in rows]
