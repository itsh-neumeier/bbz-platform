"""DWD local-observations adapter (roadmap E18-04): the POI ``-BEOB.csv`` feed is
parsed (latin-1, semicolon, decimal comma, `---` = missing) and the newest row
normalised to the E18-06 observation contract. A place without a station yields
nothing ("keine Daten"); one failing station is skipped, all-fail raises.

Fixtures under ``fixtures/poi/`` are **real** DWD POI CSVs, trimmed to 5 rows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.dwd.adapter import build
from integrations.dwd.observations import (
    DwdObservationsClient,
    DwdObservationsError,
    parse_poi_csv,
)

_FX = Path(__file__).resolve().parent / "fixtures" / "poi"


def _csv(name: str) -> bytes:
    return (_FX / name).read_bytes()


def test_the_newest_row_of_a_real_poi_csv_normalizes() -> None:
    obs = {
        o.metric: o
        for o in parse_poi_csv(_csv("10763-BEOB.csv"), place="Nürnberg", station_ref="10763")
    }
    assert obs["temperature"].value == 14.4 and obs["temperature"].unit == "°C"
    assert obs["humidity"].value == 84.0
    assert obs["wind_speed"].value == 8.0 and obs["wind_speed"].unit == "km/h"
    assert obs["precipitation"].value == 0.0
    assert obs["pressure"].value == 1020.7
    for o in obs.values():
        assert o.place == "Nürnberg" and o.station_ref == "10763"
        assert o.observed_at.tzinfo is not None and o.observed_at.hour == 3


def test_a_missing_value_is_none_not_an_error() -> None:
    obs = {
        o.metric: o
        for o in parse_poi_csv(_csv("10761-BEOB.csv"), place="Weißenburg", station_ref="10761")
    }
    # 10761 has no solar columns / some `---` — value is None, still emitted
    assert "temperature" in obs and obs["temperature"].value is not None
    assert all(o.value is None or isinstance(o.value, float) for o in obs.values())


def test_a_csv_with_no_data_rows_raises() -> None:
    with pytest.raises(DwdObservationsError):
        parse_poi_csv(
            b"surface observations;x\n10763;Unit\nDatum;Uhrzeit (UTC)\n",
            place="x",
            station_ref="10763",
        )


class _StubObs(DwdObservationsClient):
    def __init__(self, by_station: dict[str, bytes], *, fail: set[str] | None = None) -> None:
        super().__init__("https://example.invalid/poi/")
        self._by = by_station
        self._fail = fail or set()

    def _get(self, station_id: str) -> bytes:
        if station_id in self._fail or station_id not in self._by:
            raise DwdObservationsError(f"404 {station_id}")
        return self._by[station_id]


async def test_get_observations_reports_one_reading_set_per_place_with_a_station() -> None:
    provider = build(
        {
            "places": [
                {"name": "Nürnberg", "poi_station_id": "10763"},
                {"name": "Fürth", "poi_station_id": "10763"},
                {"name": "Ansbach"},  # no station -> "keine Daten"
            ]
        }
    )
    provider._observations_client = _StubObs({"10763": _csv("10763-BEOB.csv")})  # type: ignore[attr-defined]

    items = await provider.get_observations(station_ids=[])
    by_place = {it["place"] for it in items}
    assert by_place == {"Nürnberg", "Fürth"}  # Ansbach contributes nothing
    temps = [it for it in items if it["metric"] == "temperature"]
    assert {t["place"] for t in temps} == {"Nürnberg", "Fürth"}
    assert all(
        set(it) >= {"place", "metric", "value", "unit", "observed_at", "station_ref"}
        for it in items
    )


async def test_one_bad_station_is_skipped_but_all_bad_raises() -> None:
    provider = build(
        {
            "places": [
                {"name": "A", "poi_station_id": "10763"},
                {"name": "B", "poi_station_id": "99999"},
            ]
        }
    )
    provider._observations_client = _StubObs(  # type: ignore[attr-defined]
        {"10763": _csv("10763-BEOB.csv")}, fail={"99999"}
    )
    items = await provider.get_observations(station_ids=[])
    assert {it["place"] for it in items} == {"A"}  # B's station 404'd, skipped

    provider._observations_client = _StubObs({}, fail={"10763", "99999"})  # type: ignore[attr-defined]
    with pytest.raises(DwdObservationsError):
        await provider.get_observations(station_ids=[])
