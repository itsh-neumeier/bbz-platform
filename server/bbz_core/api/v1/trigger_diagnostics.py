"""Unmapped-source queue + trigger diagnostics API (roadmap E15-12).

A valid inbound signal the engine matched to no published rule is queued for
admin diagnosis (``GET /api/v1/trigger/unmapped``). An admin resolves an entry —
optionally binding it to a technical endpoint — via
``POST /api/v1/trigger/unmapped/{id}/resolve`` (audited ``TECHNICAL_ENDPOINT_MAPPED``).
``GET /api/v1/trigger/diagnostics`` exposes the counters.

Reads need ``technical_endpoints.view``; the resolve action needs
``technical_endpoints.manage``.
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError, ValidationError
from bbz_core.infra.models.unmapped_signals import UnmappedSignal
from bbz_core.infra.repositories.unmapped_signals import (
    MappingEndpointNotFoundError,
    UnmappedNotFoundError,
    UnmappedSignalService,
)

router = APIRouter(prefix="/trigger", tags=["trigger-diagnostics"])


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except UnmappedNotFoundError as exc:
        raise NotFoundError("unmapped-signal entry not found") from exc
    except MappingEndpointNotFoundError as exc:
        raise ValidationError("endpoint_id does not reference a technical endpoint") from exc


class UnmappedOut(BaseModel):
    id: uuid.UUID
    provider: str
    signal_type: str
    source: dict[str, object]
    occurrences: int
    first_seen_at: _dt.datetime
    last_seen_at: _dt.datetime
    resolved_at: _dt.datetime | None
    resolved_endpoint_id: uuid.UUID | None
    note: str | None


class ResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: bind the source to this technical endpoint (null = just dismiss)
    endpoint_id: uuid.UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class DiagnosticsOut(BaseModel):
    unmapped_open: int
    unmapped_resolved: int
    total_occurrences: int
    open_by_signal_type: dict[str, int]


def _out(row: UnmappedSignal) -> UnmappedOut:
    return UnmappedOut(
        id=row.id,
        provider=row.provider,
        signal_type=row.signal_type,
        source=dict(row.source or {}),
        occurrences=row.occurrences,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        resolved_at=row.resolved_at,
        resolved_endpoint_id=row.resolved_endpoint_id,
        note=row.note,
    )


def _svc(session: AsyncSession = Depends(db_session)) -> UnmappedSignalService:
    return UnmappedSignalService(session)


@router.get("/unmapped", response_model=list[UnmappedOut])
async def list_unmapped(
    include_resolved: bool = Query(default=False),
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: UnmappedSignalService = Depends(_svc),
) -> list[UnmappedOut]:
    return [_out(r) for r in await svc.list_queue(include_resolved=include_resolved)]


@router.post("/unmapped/{unmapped_id}/resolve", response_model=UnmappedOut)
async def resolve_unmapped(
    unmapped_id: uuid.UUID,
    body: ResolveIn,
    ctx: AuthContext = Depends(require("technical_endpoints.manage")),
    svc: UnmappedSignalService = Depends(_svc),
) -> UnmappedOut:
    with _translate():
        row = await svc.resolve(
            unmapped_id,
            endpoint_id=body.endpoint_id,
            note=body.note,
            actor_id=ctx.user_id,
        )
    return _out(row)


@router.get("/diagnostics", response_model=DiagnosticsOut)
async def diagnostics(
    _: AuthContext = Depends(require("technical_endpoints.view")),
    svc: UnmappedSignalService = Depends(_svc),
) -> DiagnosticsOut:
    summary = await svc.diagnostics()
    return DiagnosticsOut(
        unmapped_open=summary.open,
        unmapped_resolved=summary.resolved,
        total_occurrences=summary.total_occurrences,
        open_by_signal_type=summary.by_signal_type,
    )
