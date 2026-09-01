"""Read side of the weather store (roadmap E18-07).

Serves the Wetterlage page: the current DWD warnings, the latest observation per
place + metric, the radar frame series, and the regions we hold data for. Every
response also carries the refresh health (:class:`WeatherRefreshService.health`)
so the UI can flag stale data.

Radar frames live in a per-node in-memory cache the refresh singleton fills from
the radar adapter (E18-03); :meth:`radar_frames` returns an empty series until the
first successful refresh.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.weather import WeatherAlert, WeatherObservation

#: per-node radar frame cache: area -> ordered frames (the E18-06 refresh fills
#: this from the E18-03 adapter; bounded to the adapter's frame_count per area)
RADAR_CACHE: dict[str, list[RadarFrame]] = {}


@dataclass(frozen=True)
class RadarFrame:
    frame_time: _dt.datetime
    #: a ready WMS GetMap URL the client fetches the image by (no server-side
    #: proxy) — shape finalised by E18-03
    image_ref: str


class WeatherReadService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def alerts(self, *, region: str | None = None) -> list[WeatherAlert]:
        stmt = select(WeatherAlert).order_by(
            WeatherAlert.valid_from.desc().nullslast(), WeatherAlert.region
        )
        if region:
            stmt = stmt.where(WeatherAlert.region == region)
        return list((await self._s.execute(stmt)).scalars().all())

    async def latest_observations(self, *, place: str | None = None) -> list[WeatherObservation]:
        """The most recent value per (place, metric)."""
        stmt = select(WeatherObservation).order_by(
            WeatherObservation.place,
            WeatherObservation.metric,
            WeatherObservation.observed_at.desc(),
        )
        if place:
            stmt = stmt.where(WeatherObservation.place == place)
        rows = (await self._s.execute(stmt)).scalars().all()
        seen: set[tuple[str, str]] = set()
        latest: list[WeatherObservation] = []
        for row in rows:
            key = (row.place, row.metric)
            if key not in seen:
                seen.add(key)
                latest.append(row)
        return latest

    async def radar_frames(self, *, area: str) -> list[RadarFrame]:
        return list(RADAR_CACHE.get(area, []))

    async def regions(self) -> list[str]:
        a = (await self._s.execute(select(WeatherAlert.region).distinct())).scalars().all()
        o = (await self._s.execute(select(WeatherObservation.place).distinct())).scalars().all()
        return sorted({*a, *o})
