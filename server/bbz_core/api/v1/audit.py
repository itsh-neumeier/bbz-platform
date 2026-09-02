"""Audit read API (roadmap E04-04).

`GET /api/v1/audit` — filters (actor / target / action / time / correlation-id),
keyset pagination, `system.audit.view` required. Read-only: there is no write
route here (the log is append-only, MASTER_PROMPT §17).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.infra.repositories.audit_chain import AuditChainService
from bbz_core.infra.repositories.audit_queries import AuditQueryRepository, AuditRow

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
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    correlation_id: str | None
    event_seq_ref: int | None


class AuditPageOut(BaseModel):
    items: list[AuditEventOut]
    next_cursor: str | None


def _out(row: AuditRow) -> AuditEventOut:
    return AuditEventOut.model_validate(row, from_attributes=True)


@router.get("", response_model=AuditPageOut)
async def list_audit(
    action: str | None = None,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    correlation_id: str | None = None,
    since: _dt.datetime | None = None,
    until: _dt.datetime | None = None,
    cursor: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthContext = Depends(require("system.audit.view")),
    session: AsyncSession = Depends(db_session),
) -> AuditPageOut:
    page = await AuditQueryRepository(session).query(
        action=action,
        actor_user_id=actor_user_id,
        target_type=target_type,
        target_id=target_id,
        correlation_id=correlation_id,
        since=since,
        until=until,
        cursor=cursor,
        limit=limit,
    )
    return AuditPageOut(items=[_out(r) for r in page.items], next_cursor=page.next_cursor)


class ChainLinkOut(BaseModel):
    seq: int
    audit_event_id: uuid.UUID
    prev_hash: str
    row_hash: str
    action: str
    occurred_at_utc: str


class ChainOut(BaseModel):
    verified: bool
    checked: int
    head_seq: int
    head_hash: str
    first_bad_seq: int | None
    links: list[ChainLinkOut]
    next_after_seq: int | None


@router.get("/chain", response_model=ChainOut)
async def audit_chain(
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
    _: AuthContext = Depends(require("system.audit.view")),
    session: AsyncSession = Depends(db_session),
) -> ChainOut:
    """The tamper-evident hash chain over the audit log (E23-09) — re-verifies it
    and returns a page of links for an integrity check or export to external
    archival. Page with ``after_seq`` = the previous response's ``next_after_seq``."""
    svc = AuditChainService(session)
    result = await svc.verify()
    links = await svc.export(after_seq=after_seq, limit=limit)
    return ChainOut(
        verified=result.ok,
        checked=result.checked,
        head_seq=result.head_seq,
        head_hash=result.head_hash,
        first_bad_seq=result.first_bad_seq,
        links=[ChainLinkOut(**vars(link)) for link in links],
        next_after_seq=links[-1].seq if len(links) == limit else None,
    )
