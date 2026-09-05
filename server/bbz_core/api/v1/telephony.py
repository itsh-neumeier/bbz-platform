"""Telephony provider event ingestion (E11-03) + mock scenario driver (E11-05).

``POST /api/v1/telephony/events`` — a telephony provider / CTI gateway posts a
normalized ``telephony_event.v1`` event. Machine-to-machine: gated by
``calls.ingest_provider_events`` (a service-account permission, not granted to
any human built-in role). The event is validated, deduplicated through the
provider inbox and handed to the call aggregate.

``POST /api/v1/telephony/_mock/simulate-incoming`` drives the mock provider's
own ``simulate_incoming()`` scenario helper and pumps the events it emits
through that same ingest pipeline — E11-05's own AC ("Szenarien per API/Config
auslösbar") was never actually delivered; **no background worker drains a
telephony provider's event stream today**, mock or real, so without this a
call never becomes visible via ``GET /calls/ringing`` no matter how it started.
This endpoint exists so E07-19's Playwright suite (E11-13/14, #221/#223) can
drive a real incoming-call scenario end to end; it 404s on any non-mock
provider, so it can never do anything against a real PBX. Gated by
``calls.simulate_mock_scenario`` (also machine/E2E-only).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError, ValidationError
from bbz_core.api.rate_limit import rate_limit_by_ip
from bbz_core.infra.event_stream import notify_event_appended
from bbz_core.infra.telephony_ingest import (
    TelephonyEventRejected,
    ingest_telephony_event,
)
from bbz_core.integrations_host.providers import NoActiveProvider, active_telephony_provider

router = APIRouter(prefix="/telephony", tags=["telephony"])


class IngestOut(BaseModel):
    outcome: str  # "new" | "duplicate"
    dedupe_key: str


@router.post(
    "/events",
    response_model=IngestOut,
    dependencies=[Depends(rate_limit_by_ip("webhook"))],
)
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
    if result.outcome.value == "new":
        # wake the event stream so the ringing-queue view refreshes promptly
        # (E11-12); the call transition is already a domain event on the log.
        await notify_event_appended()
    return IngestOut(outcome=result.outcome.value, dedupe_key=result.dedupe_key)


class SimulateIncomingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    from_number: str = Field(min_length=1, max_length=32)
    to_line: str = Field(min_length=1, max_length=32)
    display_name: str | None = Field(default=None, max_length=200)


class SimulateIncomingOut(BaseModel):
    source_call_id: str


@router.post(
    "/_mock/simulate-incoming",
    response_model=SimulateIncomingOut,
    dependencies=[Depends(rate_limit_by_ip("webhook"))],
)
async def simulate_incoming_call(
    body: SimulateIncomingIn,
    _: AuthContext = Depends(require("calls.simulate_mock_scenario")),
    session: AsyncSession = Depends(db_session),
) -> SimulateIncomingOut:
    try:
        provider = await active_telephony_provider()
    except NoActiveProvider as exc:
        raise NotFoundError("no active telephony provider") from exc
    if not provider.info().mock:
        raise NotFoundError("scenario simulation is only available on a mock provider")

    source_call_id = provider.simulate_incoming(  # type: ignore[attr-defined]
        from_number=body.from_number, to_line=body.to_line, display_name=body.display_name
    )
    # the mock only queues what it emits (no background pump reads it back out
    # anywhere else, see the module docstring) — drain and feed it through the
    # exact same validated ingest path a real provider event would take.
    events = await provider.drain_events()  # type: ignore[attr-defined]

    await session.rollback()  # close the auth read tx before the ingest writes
    for ev in events:
        raw = ev.model_dump(mode="json")
        try:
            async with session.begin():
                await ingest_telephony_event(session, raw)
        except TelephonyEventRejected as exc:
            raise ValidationError(f"invalid simulated telephony event: {exc}") from exc
    await notify_event_appended()
    return SimulateIncomingOut(source_call_id=source_call_id)
