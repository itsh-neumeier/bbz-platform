"""Weather refresh singleton + health (roadmap E18-06).

One leader-elected tick (``weather-refresh``, ADR-0018) polls the active weather
integration for each capability it advertises, upserts the normalized items into
``weather_alerts`` / ``weather_observations``, and records the outcome per data
kind in ``weather_refresh_state``. Radar frames are not a DB table — the tick
records the refresh state only; the frame cache is E18-03.

Health per data kind:

* ``ok``       — a successful refresh within ``weather_stale_after_seconds``
* ``stale``    — the last success is older than the TTL (data is shown, flagged)
* ``degraded`` — the last *attempt* failed but an earlier success exists
* ``down``     — never succeeded

The refresh **never raises** into the worker: a fetch / parse failure is recorded
and the last good data stays. Normalisation of the raw DWD payloads (CAP XML /
POI CSV) is the adapters' job (E18-02 / E18-04); this module owns the internal
normalized contract, the storage, and the health.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.weather import WeatherAlert, WeatherObservation
from bbz_core.infra.models.weather_refresh import WEATHER_DATA_KINDS, WeatherRefreshState
from bbz_core.integrations_host.providers import NoActiveProvider, active_weather_provider
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)

#: SDK capability key → the data kind it feeds
_KIND_BY_CAPABILITY = {
    "weather.warnings": "warnings",
    "weather.radar": "radar",
    "weather.observations": "observations",
}

#: the normalized keys an adapter's ``get_warnings`` item must carry (E18-02)
_ALERT_FIELDS = (
    "region",
    "type",
    "level",
    "valid_from",
    "valid_to",
    "headline",
    "description",
    "source_ref",
)


class WeatherHealthStatus(StrEnum):
    OK = "ok"
    STALE = "stale"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass(frozen=True)
class KindHealth:
    data_kind: str
    status: str
    last_success_at: _dt.datetime | None
    last_attempt_at: _dt.datetime | None
    last_error: str | None
    item_count: int | None
    age_seconds: float | None


@dataclass(frozen=True)
class WeatherHealth:
    integration_id: str
    overall: str
    checked_at: _dt.datetime
    kinds: list[KindHealth]


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _as_dt(value: Any) -> _dt.datetime | None:
    if value is None or isinstance(value, _dt.datetime):
        return value
    try:
        parsed = _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=_dt.UTC)


class WeatherRefreshService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- the tick -----------------------------------------------------------

    async def refresh(self) -> int:
        """Poll every advertised capability, store, record state. Returns the
        total items ingested. Never raises."""
        try:
            provider = await active_weather_provider()
        except NoActiveProvider:
            return 0

        settings = get_settings()
        region = settings.weather_integration_id  # label only; the adapter knows its region
        caps = provider.capabilities()
        total = 0

        if caps.has("weather.warnings"):
            total += await self._run(
                "warnings",
                lambda: provider.get_warnings(region=region),
                self._store_warnings,
            )
        if caps.has("weather.observations"):
            total += await self._run(
                "observations",
                lambda: provider.get_observations(station_ids=self._station_ids()),
                self._store_observations,
            )
        if caps.has("weather.radar"):
            total += await self._run(
                "radar",
                lambda: provider.get_radar_frames(area=region),
                self._count_only,
            )
        return total

    async def _run(
        self,
        kind: str,
        fetch: Callable[[], Awaitable[Sequence[Any]]],
        store: Callable[[Sequence[Any]], Awaitable[int]],
    ) -> int:
        attempt_at = _now()
        try:
            items = list(await fetch())
            await self._s.rollback()
            async with self._s.begin():
                count = await store(items)
                await self._record(
                    kind, attempt_at=attempt_at, success_at=attempt_at, item_count=count
                )
            return count
        except Exception as exc:  # a bad fetch/parse must not kill the worker
            _log.warning("weather_refresh_failed", data_kind=kind, error=repr(exc))
            await self._s.rollback()
            async with self._s.begin():
                await self._record(
                    kind, attempt_at=attempt_at, error=f"{type(exc).__name__}: {exc}"
                )
            return 0

    def _station_ids(self) -> list[str]:
        return []  # the adapter resolves places → stations from its own config (E18-04)

    async def _count_only(self, items: Sequence[Any]) -> int:
        return len(items)

    # --- storage ----------------------------------------------------------

    async def _store_warnings(self, items: Sequence[Any]) -> int:
        rows = [r for it in items if (r := self._alert_row(it)) is not None]
        now = _now()
        kept: list[Any] = []
        for r in rows:
            kept_id = (
                await self._s.execute(
                    pg_insert(WeatherAlert)
                    .values(received_at=now, **r)
                    .on_conflict_do_update(
                        index_elements=["source_ref", "region"],
                        set_={**r, "received_at": now, "updated_at": now},
                    )
                    .returning(WeatherAlert.id)
                )
            ).scalar_one()
            kept.append(kept_id)
        # a full successful fetch is authoritative — drop warnings DWD dropped
        await self._s.execute(
            delete(WeatherAlert).where(WeatherAlert.id.notin_(kept))
            if kept
            else delete(WeatherAlert)
        )
        return len(rows)

    async def _store_observations(self, items: Sequence[Any]) -> int:
        rows = [r for it in items if (r := self._observation_row(it)) is not None]
        for r in rows:
            await self._s.execute(
                pg_insert(WeatherObservation)
                .values(**r)
                .on_conflict_do_update(
                    index_elements=["place", "metric", "observed_at"],
                    set_={"value": r["value"], "unit": r["unit"], "station_ref": r["station_ref"]},
                )
            )
        return len(rows)

    def _alert_row(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        try:
            row = {k: item.get(k) for k in _ALERT_FIELDS}
            if not row["region"] or not row["type"] or not row["source_ref"]:
                return None
            row["level"] = str(row["level"]) if row["level"] is not None else ""
            row["valid_from"] = _as_dt(row["valid_from"])
            row["valid_to"] = _as_dt(row["valid_to"])
            return row
        except (AttributeError, TypeError):
            return None

    def _observation_row(self, item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        place, metric = item.get("place"), item.get("metric")
        observed_at = _as_dt(item.get("observed_at"))
        if not place or not metric or observed_at is None:
            return None
        value = item.get("value")
        return {
            "place": str(place),
            "metric": str(metric),
            "value": float(value) if isinstance(value, int | float) else None,
            "unit": str(item.get("unit") or ""),
            "observed_at": observed_at,
            "station_ref": str(item.get("station_ref") or ""),
        }

    # --- state + health -------------------------------------------------

    async def _record(
        self,
        kind: str,
        *,
        attempt_at: _dt.datetime,
        success_at: _dt.datetime | None = None,
        item_count: int | None = None,
        error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "data_kind": kind,
            "last_attempt_at": attempt_at,
            "last_error": error,
            "updated_at": attempt_at,
        }
        set_: dict[str, Any] = {
            "last_attempt_at": attempt_at,
            "last_error": error,
            "updated_at": attempt_at,
        }
        if success_at is not None:
            values["last_success_at"] = success_at
            values["last_item_count"] = item_count
            set_["last_success_at"] = success_at
            set_["last_item_count"] = item_count
        await self._s.execute(
            pg_insert(WeatherRefreshState)
            .values(**values)
            .on_conflict_do_update(index_elements=["data_kind"], set_=set_)
        )

    async def health(self) -> WeatherHealth:
        try:
            integration_id = get_settings().weather_integration_id
            provider = await active_weather_provider()
            active_kinds = {
                _KIND_BY_CAPABILITY[c]
                for c in _KIND_BY_CAPABILITY
                if provider.capabilities().has(c)
            }
        except NoActiveProvider:
            return WeatherHealth(
                integration_id=get_settings().weather_integration_id,
                overall=WeatherHealthStatus.DOWN.value,
                checked_at=_now(),
                kinds=[],
            )

        ttl = get_settings().weather_stale_after_seconds
        rows = {
            r.data_kind: r
            for r in (await self._s.execute(select(WeatherRefreshState))).scalars().all()
        }
        now = _now()
        kinds: list[KindHealth] = []
        for kind in WEATHER_DATA_KINDS:
            if kind not in active_kinds:
                continue
            st = rows.get(kind)
            kinds.append(_kind_health(kind, st, ttl=ttl, now=now))

        order = [
            WeatherHealthStatus.DOWN.value,
            WeatherHealthStatus.DEGRADED.value,
            WeatherHealthStatus.STALE.value,
            WeatherHealthStatus.OK.value,
        ]
        overall = (
            min((k.status for k in kinds), key=order.index)
            if kinds
            else WeatherHealthStatus.DOWN.value
        )
        return WeatherHealth(
            integration_id=integration_id, overall=overall, checked_at=now, kinds=kinds
        )


def _kind_health(
    kind: str, st: WeatherRefreshState | None, *, ttl: int, now: _dt.datetime
) -> KindHealth:
    if st is None or st.last_success_at is None:
        return KindHealth(kind, WeatherHealthStatus.DOWN.value, None, None, None, None, None)
    age = (now - st.last_success_at).total_seconds()
    errored_since_success = (
        st.last_error is not None
        and st.last_attempt_at is not None
        and st.last_attempt_at > st.last_success_at
    )
    if errored_since_success:
        status = WeatherHealthStatus.DEGRADED.value
    elif age > ttl:
        status = WeatherHealthStatus.STALE.value
    else:
        status = WeatherHealthStatus.OK.value
    return KindHealth(
        data_kind=kind,
        status=status,
        last_success_at=st.last_success_at,
        last_attempt_at=st.last_attempt_at,
        last_error=st.last_error,
        item_count=st.last_item_count,
        age_seconds=age,
    )
