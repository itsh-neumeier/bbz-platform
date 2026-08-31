"""Weather refresh singleton + health (roadmap E18-06): one leader-elected tick
polls the weather integration, upserts the DWD snapshot, and records per-kind
state; health goes `stale` past the TTL, `degraded` on a failed attempt, `down`
when nothing ever succeeded. A fetch failure never raises and keeps the last
good data.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.weather import WeatherAlert, WeatherObservation
from bbz_core.infra.models.weather_refresh import WeatherRefreshState
from bbz_core.infra.repositories import weather_refresh as mod
from bbz_core.infra.repositories.weather_refresh import WeatherRefreshService

_NOW = _dt.datetime(2026, 9, 1, 12, 0, tzinfo=_dt.UTC)


class _Caps:
    def __init__(self, keys: set[str]) -> None:
        self._keys = keys

    def has(self, key: str) -> bool:
        return key in self._keys


class _StubWeather:
    """A weather provider that returns whatever it is told to (or raises)."""

    def __init__(
        self,
        *,
        caps: set[str] | None = None,
        warnings: list[dict[str, Any]] | None = None,
        observations: list[dict[str, Any]] | None = None,
        radar: list[Any] | None = None,
        fail: set[str] | None = None,
    ) -> None:
        self._caps = caps or {"weather.warnings", "weather.observations", "weather.radar"}
        self._warnings = warnings or []
        self._observations = observations or []
        self._radar = radar or []
        self._fail = fail or set()

    def capabilities(self) -> _Caps:
        return _Caps(self._caps)

    async def get_warnings(self, *, region: str) -> list[dict[str, Any]]:
        if "warnings" in self._fail:
            raise RuntimeError("dwd warnings feed 503")
        return self._warnings

    async def get_observations(self, *, station_ids: list[str]) -> list[dict[str, Any]]:
        if "observations" in self._fail:
            raise RuntimeError("dwd poi timeout")
        return self._observations

    async def get_radar_frames(self, *, area: str) -> list[Any]:
        if "radar" in self._fail:
            raise RuntimeError("dwd wms down")
        return self._radar


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


@pytest.fixture(autouse=True)
def _short_ttl(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("BBZ_WEATHER_STALE_AFTER_SECONDS", "600")
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    yield
    settings_mod.get_settings.cache_clear()


def _use(monkeypatch: pytest.MonkeyPatch, provider: object) -> None:
    async def _active() -> object:
        return provider

    monkeypatch.setattr(mod, "active_weather_provider", _active)


def _warning(source_ref: str, region: str = "Nürnberg", **kw: Any) -> dict[str, Any]:
    base = {
        "region": region,
        "type": "Sturmböen",
        "level": 2,
        "valid_from": _NOW.isoformat(),
        "valid_to": (_NOW + _dt.timedelta(hours=6)).isoformat(),
        "headline": "Amtliche Warnung",
        "description": "Böen 70 km/h.",
        "source_ref": source_ref,
    }
    base.update(kw)
    return base


def _obs(place: str, metric: str, value: float, unit: str) -> dict[str, Any]:
    return {
        "place": place,
        "metric": metric,
        "value": value,
        "unit": unit,
        "observed_at": _NOW.isoformat(),
        "station_ref": "10763",
    }


async def test_a_successful_refresh_stores_the_snapshot_and_is_ok(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(
        monkeypatch,
        _StubWeather(
            warnings=[_warning("cap-1"), _warning("cap-2", region="Fürth")],
            observations=[_obs("Erlangen", "temperature", 17.1, "°C")],
            radar=["frame-a", "frame-b", "frame-c"],
        ),
    )
    total = await WeatherRefreshService(s).refresh()
    assert total == 6  # 2 warnings + 1 observation stored + 3 radar frames seen

    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(WeatherAlert))).scalar_one() == 2
    assert (await s.execute(select(func.count()).select_from(WeatherObservation))).scalar_one() == 1

    health = await WeatherRefreshService(s).health()
    assert health.overall == "ok"
    assert {k.data_kind for k in health.kinds} == {"warnings", "observations", "radar"}
    assert all(k.status == "ok" for k in health.kinds)
    assert next(k for k in health.kinds if k.data_kind == "radar").item_count == 3


async def test_the_refresh_is_idempotent_and_drops_warnings_dwd_stopped_publishing(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(
        monkeypatch,
        _StubWeather(caps={"weather.warnings"}, warnings=[_warning("a"), _warning("b")]),
    )
    await WeatherRefreshService(s).refresh()
    await WeatherRefreshService(s).refresh()  # same feed again
    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(WeatherAlert))).scalar_one() == 2

    # DWD now only publishes "a"
    _use(monkeypatch, _StubWeather(caps={"weather.warnings"}, warnings=[_warning("a")]))
    await WeatherRefreshService(s).refresh()
    await s.rollback()
    refs = [r for (r,) in (await s.execute(select(WeatherAlert.source_ref))).all()]
    assert refs == ["a"]


async def test_health_goes_stale_after_the_ttl(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, _StubWeather(caps={"weather.warnings"}, warnings=[_warning("a")]))
    await WeatherRefreshService(s).refresh()

    # age the last success past the 600 s TTL
    await s.rollback()
    async with s.begin():
        await s.execute(
            update(WeatherRefreshState)
            .where(WeatherRefreshState.data_kind == "warnings")
            .values(
                last_success_at=_dt.datetime.now(_dt.UTC) - _dt.timedelta(hours=2),
                last_attempt_at=_dt.datetime.now(_dt.UTC) - _dt.timedelta(hours=2),
            )
        )
    health = await WeatherRefreshService(s).health()
    assert health.overall == "stale"
    assert health.kinds[0].status == "stale" and health.kinds[0].age_seconds > 600


async def test_a_failed_attempt_after_a_success_is_degraded_and_keeps_the_data(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, _StubWeather(caps={"weather.warnings"}, warnings=[_warning("a")]))
    await WeatherRefreshService(s).refresh()

    _use(monkeypatch, _StubWeather(caps={"weather.warnings"}, fail={"warnings"}))
    total = await WeatherRefreshService(s).refresh()
    assert total == 0  # the failed fetch ingested nothing and did not raise

    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(WeatherAlert))).scalar_one() == 1
    st = (await s.execute(select(WeatherRefreshState))).scalar_one()
    assert st.last_error is not None and "503" in st.last_error

    health = await WeatherRefreshService(s).health()
    assert health.overall == "degraded" and health.kinds[0].status == "degraded"


async def test_never_succeeded_is_down(s: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, _StubWeather(caps={"weather.warnings"}, fail={"warnings"}))
    await WeatherRefreshService(s).refresh()
    health = await WeatherRefreshService(s).health()
    assert health.overall == "down" and health.kinds[0].status == "down"


async def test_an_unconfigured_system_is_a_no_op(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bbz_core.integrations_host.providers import NoActiveProvider

    async def _none() -> object:
        raise NoActiveProvider("no weather integration")

    monkeypatch.setattr(mod, "active_weather_provider", _none)
    assert await WeatherRefreshService(s).refresh() == 0
    assert (await WeatherRefreshService(s).health()).overall == "down"


async def test_the_real_dwd_stub_refresh_records_errors_without_crashing(s: AsyncSession) -> None:
    """Against the shipped dwd scaffold (get_* raise DwdNotImplementedError) the
    tick is safe and every kind ends up `down`."""
    from bbz_core.integrations_host.providers import reset_provider_cache

    reset_provider_cache()
    total = await WeatherRefreshService(s).refresh()
    assert total == 0
    await s.rollback()
    states = (await s.execute(select(WeatherRefreshState))).scalars().all()
    assert {st.data_kind for st in states} == {"warnings", "radar", "observations"}
    assert all(st.last_success_at is None and st.last_error for st in states)
    assert (await WeatherRefreshService(s).health()).overall == "down"
    reset_provider_cache()
