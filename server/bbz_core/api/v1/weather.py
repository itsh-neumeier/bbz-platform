"""Weather API for the Wetterlage page (roadmap E18-07 / E18-08).

Read-only DWD data for Mittelfranken — current warnings, latest observations, the
radar frame series, and the regions we hold data for — plus "create a BBZ event
from a warning" (E18-08). Every read response carries the refresh ``health``
(E18-06) so the client can flag stale data. All times UTC (ADR-0017).

Attribution: DWD data must be shown with "Deutscher Wetterdienst" (ADR-0026).
"""

from __future__ import annotations

import contextlib
import datetime as _dt
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.api.authz import require
from bbz_core.api.deps import AuthContext, db_session
from bbz_core.api.errors import NotFoundError
from bbz_core.api.idempotency import CommandEnvelope, command_envelope
from bbz_core.domain.events import EventPriority
from bbz_core.infra.models.weather import WeatherAlert, WeatherObservation
from bbz_core.infra.repositories.weather_events import (
    WeatherAlertNotFoundError,
    WeatherEventService,
)
from bbz_core.infra.repositories.weather_read import RadarFrame, WeatherReadService
from bbz_core.infra.repositories.weather_refresh import WeatherRefreshService
from bbz_core.settings import get_settings

router = APIRouter(prefix="/weather", tags=["weather"])

ATTRIBUTION = "Deutscher Wetterdienst"


@contextlib.contextmanager
def _translate() -> Iterator[None]:
    try:
        yield
    except WeatherAlertNotFoundError as exc:
        raise NotFoundError("weather alert not found") from exc


class KindHealthOut(BaseModel):
    data_kind: str
    status: str
    last_success_at: _dt.datetime | None
    last_error: str | None
    age_seconds: float | None


class HealthOut(BaseModel):
    overall: str
    checked_at: _dt.datetime
    kinds: list[KindHealthOut]


class AlertOut(BaseModel):
    id: uuid.UUID
    region: str
    type: str
    level: str
    valid_from: _dt.datetime | None
    valid_to: _dt.datetime | None
    headline: str | None
    description: str | None
    source_ref: str
    received_at: _dt.datetime


class ObservationOut(BaseModel):
    place: str
    metric: str
    value: float | None
    unit: str
    observed_at: _dt.datetime
    station_ref: str


class RadarFrameOut(BaseModel):
    frame_time: _dt.datetime
    image_ref: str


class AlertsResponse(BaseModel):
    attribution: str = ATTRIBUTION
    health: HealthOut
    alerts: list[AlertOut]


class ObservationsResponse(BaseModel):
    attribution: str = ATTRIBUTION
    health: HealthOut
    observations: list[ObservationOut]


class RadarResponse(BaseModel):
    attribution: str = ATTRIBUTION
    health: HealthOut
    area: str
    frames: list[RadarFrameOut]


class RegionsResponse(BaseModel):
    regions: list[str]


async def _health(session: AsyncSession) -> HealthOut:
    h = await WeatherRefreshService(session).health()
    return HealthOut(
        overall=h.overall,
        checked_at=h.checked_at,
        kinds=[
            KindHealthOut(
                data_kind=k.data_kind,
                status=k.status,
                last_success_at=k.last_success_at,
                last_error=k.last_error,
                age_seconds=k.age_seconds,
            )
            for k in h.kinds
        ],
    )


def _alert_out(a: WeatherAlert) -> AlertOut:
    return AlertOut(
        id=a.id,
        region=a.region,
        type=a.type,
        level=a.level,
        valid_from=a.valid_from,
        valid_to=a.valid_to,
        headline=a.headline,
        description=a.description,
        source_ref=a.source_ref,
        received_at=a.received_at,
    )


def _obs_out(o: WeatherObservation) -> ObservationOut:
    return ObservationOut(
        place=o.place,
        metric=o.metric,
        value=o.value,
        unit=o.unit,
        observed_at=o.observed_at,
        station_ref=o.station_ref,
    )


def _frame_out(f: RadarFrame) -> RadarFrameOut:
    return RadarFrameOut(frame_time=f.frame_time, image_ref=f.image_ref)


@router.get("/alerts", response_model=AlertsResponse)
async def list_alerts(
    region: str | None = Query(default=None, max_length=120),
    _: AuthContext = Depends(require("weather.view")),
    session: AsyncSession = Depends(db_session),
) -> AlertsResponse:
    svc = WeatherReadService(session)
    return AlertsResponse(
        health=await _health(session),
        alerts=[_alert_out(a) for a in await svc.alerts(region=region)],
    )


@router.get("/observations", response_model=ObservationsResponse)
async def list_observations(
    place: str | None = Query(default=None, max_length=120),
    _: AuthContext = Depends(require("weather.view")),
    session: AsyncSession = Depends(db_session),
) -> ObservationsResponse:
    svc = WeatherReadService(session)
    return ObservationsResponse(
        health=await _health(session),
        observations=[_obs_out(o) for o in await svc.latest_observations(place=place)],
    )


@router.get("/radar", response_model=RadarResponse)
async def radar(
    area: str | None = Query(default=None, max_length=64),
    _: AuthContext = Depends(require("weather.view")),
    session: AsyncSession = Depends(db_session),
) -> RadarResponse:
    area = area or get_settings().weather_radar_area
    svc = WeatherReadService(session)
    return RadarResponse(
        health=await _health(session),
        area=area,
        frames=[_frame_out(f) for f in await svc.radar_frames(area=area)],
    )


@router.get("/regions", response_model=RegionsResponse)
async def regions(
    _: AuthContext = Depends(require("weather.view")),
    session: AsyncSession = Depends(db_session),
) -> RegionsResponse:
    return RegionsResponse(regions=await WeatherReadService(session).regions())


# --- create a BBZ event from a warning (E18-08) ---------------------------


class CreateEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority: EventPriority
    #: the operator's operational assessment ("betriebliche Bewertung")
    assessment: str | None = Field(default=None, max_length=20_000)


class CreateEventOut(BaseModel):
    event_id: uuid.UUID
    weather_alert_id: uuid.UUID
    source_ref: str
    priority: str
    created: bool


@router.post(
    "/alerts/{alert_id}/create-event",
    response_model=CreateEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_event_from_alert(
    alert_id: uuid.UUID,
    body: CreateEventIn,
    response: Response,
    ctx: AuthContext = Depends(require("weather.create_event")),
    env: CommandEnvelope = Depends(command_envelope),
    session: AsyncSession = Depends(db_session),
) -> CreateEventOut:
    with _translate():
        result = await WeatherEventService(session).create_from_alert(
            alert_id=alert_id,
            priority=body.priority,
            assessment=body.assessment,
            command_id=env.command_id,
            actor_id=ctx.user_id,
        )
    response.headers["Location"] = f"/api/v1/events/{result.event_id}"
    return CreateEventOut(
        event_id=result.event_id,
        weather_alert_id=result.weather_alert_id,
        source_ref=result.source_ref,
        priority=result.priority,
        created=result.created,
    )
