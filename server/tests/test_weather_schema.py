"""weather_alerts / weather_observations schema (roadmap E18-05)."""

from __future__ import annotations

import datetime as _dt
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import Base
from bbz_core.infra.models.weather import WeatherAlert, WeatherObservation

_NOW = _dt.datetime(2026, 9, 1, 12, 0, tzinfo=_dt.UTC)


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


def test_both_tables_are_registered() -> None:
    md = Base.metadata.tables
    assert {"weather_alerts", "weather_observations"} <= set(md)
    # snapshots of DWD state — no FK into BBZ's authoritative records
    assert not md["weather_alerts"].foreign_keys
    assert not md["weather_observations"].foreign_keys


async def test_an_alert_round_trips_with_utc_times(s: AsyncSession) -> None:
    a = WeatherAlert(
        region="Nürnberg",
        type="Sturmböen",
        level="2",
        valid_from=_NOW,
        valid_to=_NOW + _dt.timedelta(hours=6),
        headline="Amtliche Warnung vor Sturmböen",
        description="Böen 65 km/h aus Südwest.",
        source_ref="cap-2026-09-01-abc",
        received_at=_NOW,
    )
    s.add(a)
    await s.commit()
    got = (await s.execute(select(WeatherAlert))).scalar_one()
    assert got.valid_from == _NOW and got.valid_from.tzinfo is not None
    assert got.created_at.tzinfo is not None


async def test_same_cap_alert_two_regions_is_allowed_but_not_the_same_region_twice(
    s: AsyncSession,
) -> None:
    for region in ("Nürnberg", "Fürth"):
        s.add(
            WeatherAlert(
                region=region,
                type="Gewitter",
                level="1",
                source_ref="cap-multi",
                received_at=_NOW,
            )
        )
    await s.commit()
    assert len((await s.execute(select(WeatherAlert))).scalars().all()) == 2

    s.add(
        WeatherAlert(
            region="Nürnberg", type="Gewitter", level="1", source_ref="cap-multi", received_at=_NOW
        )
    )
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_observations_are_unique_per_place_metric_time(s: AsyncSession) -> None:
    s.add(
        WeatherObservation(
            place="Erlangen",
            metric="temperature",
            value=17.4,
            unit="°C",
            observed_at=_NOW,
            station_ref="10763",
        )
    )
    await s.commit()
    # a different metric at the same time is fine
    s.add(
        WeatherObservation(
            place="Erlangen",
            metric="wind_speed",
            value=3.1,
            unit="m/s",
            observed_at=_NOW,
            station_ref="10763",
        )
    )
    await s.commit()
    # the same place+metric+time is a conflict (idempotent upsert key)
    s.add(
        WeatherObservation(
            place="Erlangen",
            metric="temperature",
            value=99.0,
            unit="°C",
            observed_at=_NOW,
            station_ref="10763",
        )
    )
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_a_missing_value_is_allowed_no_data(s: AsyncSession) -> None:
    s.add(
        WeatherObservation(
            place="Ansbach",
            metric="precipitation",
            value=None,
            unit="mm",
            observed_at=_NOW,
            station_ref="10788",
        )
    )
    await s.commit()
    got = (
        await s.execute(select(WeatherObservation).where(WeatherObservation.place == "Ansbach"))
    ).scalar_one()
    assert got.value is None
