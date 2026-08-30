"""Telephony provider event ingestion (E11-03).

``POST /api/v1/telephony/events`` — a telephony provider / CTI gateway posts a
normalized ``telephony_event.v1`` event. Machine-to-machine: gated by
``calls.ingest_provider_events`` (a service-account permission, not granted to
any human built-in role). The event is validated, deduplicated through the
provider inbox and handed to the call aggregate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import ValidationError
from bbz_core.infra.telephony_ingest import (
    TelephonyEventRejected,
    ingest_telephony_event,
)

router = APIRouter(prefix="/telephony", tags=["telephony"])


class IngestOut(BaseModel):
    outcome: str  # "new" | "duplicate"
    dedupe_key: str


@router.post("/events", response_model=IngestOut)
async def ingest_event(
    event: dict[str, Any],
    _: AuthContext = Depends(require("calls.ingest_provider_events")),
    session: AsyncSession = Depends(db_session),
) -> IngestOut:
    await session.rollback()  # close the auth read tx before the ingest write tx
    try:
        async with session.begin():
            result = await ingest_telephony_event(session, event)
    except TelephonyEventRejected as exc:
        raise ValidationError(f"invalid telephony event: {exc}") from exc
    return IngestOut(outcome=result.outcome.value, dedupe_key=result.dedupe_key)
