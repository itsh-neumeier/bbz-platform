"""Telephony line status API (roadmap E11-07).

``GET /lines`` — the available lines and their current state (§13.1). State is
maintained from the normalized ``LINE_IN_SERVICE`` / ``LINE_OUT_OF_SERVICE``
provider events (``LineStatusService``); an outage also appears on the event
stream as a ``LINE_*`` domain event. Read-only, ``calls.view``.
"""

from __future__ import annotations

import datetime as _dt
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.infra.models.telephony import Line

router = APIRouter(prefix="/lines", tags=["telephony"])


class LineOut(BaseModel):
    id: uuid.UUID
    provider: str
    external_id: str
    label: str | None
    state: str
    workplace_id: uuid.UUID | None
    updated_at: _dt.datetime


class LinesOut(BaseModel):
    lines: list[LineOut]


@router.get("", response_model=LinesOut)
async def list_lines(
    provider: str | None = Query(default=None),
    _: AuthContext = Depends(require("calls.view")),
    session: AsyncSession = Depends(db_session),
) -> LinesOut:
    stmt = select(Line).order_by(Line.provider.asc(), Line.external_id.asc())
    if provider is not None:
        stmt = stmt.where(Line.provider == provider)
    rows = (await session.execute(stmt)).scalars().all()
    return LinesOut(lines=[LineOut.model_validate(r, from_attributes=True) for r in rows])
