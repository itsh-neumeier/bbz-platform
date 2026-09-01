"""DWD local-observations client + POI CSV parser (roadmap E18-04, ADR-0026).

Source: ``opendata.dwd.de/weather/weather_reports/poi/<station_id>-BEOB.csv`` —
one file per DWD SYNOP station, ~24 h of hourly values, newest row first.

Format: semicolon CSV, **latin-1**, decimal **comma**, ``---`` = missing. Three
header rows:

1. ``surface observations;Parameter description;<param_key>;…`` — the machine keys
2. ``<station_id>;Unit;<unit>;…``
3. ``Datum;Uhrzeit (UTC);<german label>;…``

The newest data row is normalised to the E18-06 observation contract
(``place, metric, value, unit, observed_at, station_ref``). A missing station
(``poi_station_id`` empty) yields nothing — "keine Daten", not an error.
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://opendata.dwd.de/weather/weather_reports/poi/"

_MAX_BYTES = 2 * 1024 * 1024
_TIMEOUT = 30

#: DWD POI param key → (normalized metric, unit). Kept small + operationally
#: relevant for the Wetterlage tiles (§13.12).
_METRICS: dict[str, tuple[str, str]] = {
    "dry_bulb_temperature_at_2_meter_above_ground": ("temperature", "°C"),
    "relative_humidity": ("humidity", "%"),
    "mean_wind_speed_during last_10_min_at_10_meters_above_ground": ("wind_speed", "km/h"),
    "maximum_wind_speed_last_hour": ("wind_gust", "km/h"),
    "precipitation_amount_last_hour": ("precipitation", "mm"),
    "pressure_reduced_to_mean_sea_level": ("pressure", "hPa"),
    "cloud_cover_total": ("cloud_cover", "%"),
}


class DwdObservationsError(RuntimeError):
    """A fetch or parse of a DWD POI CSV failed."""


@dataclass(frozen=True)
class NormalizedObservation:
    place: str
    metric: str
    value: float | None
    unit: str
    observed_at: _dt.datetime
    station_ref: str

    def as_item(self) -> dict[str, object]:
        return {
            "place": self.place,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
            "observed_at": self.observed_at.isoformat(),
            "station_ref": self.station_ref,
        }


def _num(raw: str) -> float | None:
    raw = raw.strip()
    if not raw or raw == "---":
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _observed_at(datum: str, uhrzeit: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.strptime(
            f"{datum.strip()} {uhrzeit.strip()}", "%d.%m.%y %H:%M"
        ).replace(tzinfo=_dt.UTC)
    except ValueError:
        return None


def parse_poi_csv(
    csv_bytes: bytes | str, *, place: str, station_ref: str
) -> list[NormalizedObservation]:
    """Normalise the newest data row of a POI ``-BEOB.csv`` to observations."""
    text = csv_bytes.decode("latin-1") if isinstance(csv_bytes, bytes) else csv_bytes
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    if len(rows) < 4:
        raise DwdObservationsError(f"POI CSV for {station_ref} has no data rows")
    keys = rows[0]
    latest = rows[3]  # newest first, right after the 3 header rows
    observed_at = _observed_at(latest[0], latest[1])
    if observed_at is None:
        raise DwdObservationsError(f"POI CSV for {station_ref}: unparseable timestamp {latest[:2]}")

    idx = {k: i for i, k in enumerate(keys)}
    out: list[NormalizedObservation] = []
    for key, (metric, unit) in _METRICS.items():
        i = idx.get(key)
        if i is None or i >= len(latest):
            continue
        out.append(
            NormalizedObservation(
                place=place,
                metric=metric,
                value=_num(latest[i]),
                unit=unit,
                observed_at=observed_at,
                station_ref=station_ref,
            )
        )
    return out


class DwdObservationsClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: int = _TIMEOUT) -> None:
        self._base = base_url if base_url.endswith("/") else base_url + "/"
        self._timeout = timeout

    def _get(self, station_id: str) -> bytes:
        url = f"{self._base}{station_id}-BEOB.csv"
        req = urllib.request.Request(url, headers={"User-Agent": "bbz-platform/dwd"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data: bytes = resp.read(_MAX_BYTES + 1)
        except (OSError, ValueError) as exc:
            raise DwdObservationsError(f"GET {url} failed: {exc}") from exc
        if len(data) > _MAX_BYTES:
            raise DwdObservationsError(f"POI CSV {url} exceeds {_MAX_BYTES} bytes")
        return data

    def fetch(self, *, place: str, station_id: str) -> list[NormalizedObservation]:
        return parse_poi_csv(self._get(station_id), place=place, station_ref=station_id)
