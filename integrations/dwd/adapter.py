"""``dwd`` adapter (roadmap E18-01 scaffold, E18-02 warnings).

A protocol-conformant :class:`~bbz_integration_sdk.providers.WeatherProvider` for
Mittelfranken over DWD's public open-data services (ADR-0026).

* :meth:`get_warnings` — **E18-02**: the CAP 1.2 DISTRICT feed
  (``opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/``), filtered to the
  configured places' warncells, normalised to the E18-06 item contract.
* :meth:`get_radar_frames` — E18-03 (GeoServer WMS) — still raises.
* :meth:`get_observations` — E18-04 (POI CSV) — still raises.

Only outbound HTTPS to ``opendata.dwd.de`` / ``maps.dwd.de``; no credentials, no
PII. Every DWD-derived value carries the "Deutscher Wetterdienst" attribution.
The blocking HTTP/unzip runs in a worker thread so the event loop is free.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo
from integrations.dwd.observations import DEFAULT_BASE_URL as _OBS_BASE_URL
from integrations.dwd.observations import DwdObservationsClient
from integrations.dwd.warnings import DEFAULT_BASE_URL, DwdWarningsClient

#: DWD open-data capability → the SDK capability it maps to
_CAPABILITY_BY_KEY = {
    "weather.warnings": Capability.WEATHER_WARNINGS,
    "weather.radar": Capability.WEATHER_RADAR,
    "weather.observations": Capability.WEATHER_OBSERVATIONS,
}

#: MASTER_PROMPT §10 — the operational places for Mittelfranken
DEFAULT_PLACES: tuple[str, ...] = (
    "Nürnberg",
    "Fürth",
    "Erlangen",
    "Schwabach",
    "Ansbach",
    "Neustadt a.d. Aisch",
)

ATTRIBUTION = "Deutscher Wetterdienst"


class DwdNotImplementedError(RuntimeError):
    """A DWD data method was called before its adapter epic (E18-03/04) landed."""


@lru_cache
def _bundled_places() -> dict[str, dict[str, Any]]:
    """``mittelfranken.json`` — place name → {warncell_ids, poi_station_id}."""
    raw = json.loads((files("integrations.dwd.data") / "mittelfranken.json").read_text("utf-8"))
    return {p["name"]: p for p in raw.get("places", [])}


@dataclass(frozen=True)
class DwdPlace:
    name: str
    warncell_ids: tuple[str, ...] = ()
    poi_station_id: str = ""


@dataclass
class DwdConfig:
    instance_id: str = "dwd-1"
    region: str = "mittelfranken"
    enabled_capabilities: tuple[str, ...] = tuple(_CAPABILITY_BY_KEY)
    places: tuple[DwdPlace, ...] = field(
        default_factory=lambda: tuple(_place(name) for name in DEFAULT_PLACES)
    )
    warnings: dict[str, Any] = field(default_factory=dict)
    radar: dict[str, Any] = field(default_factory=dict)
    observations: dict[str, Any] = field(default_factory=dict)

    def warncell_ids(self) -> set[str]:
        return {wc for p in self.places for wc in p.warncell_ids}


def _place(name: str, cfg: dict[str, Any] | None = None) -> DwdPlace:
    bundled = _bundled_places().get(name, {})
    cfg = cfg or {}
    ids = cfg.get("warncell_ids") or bundled.get("warncell_ids") or []
    single = cfg.get("warncell_id") or bundled.get("warncell_id")
    if single and single not in ids:
        ids = [*ids, single]
    return DwdPlace(
        name=name,
        warncell_ids=tuple(str(i) for i in ids if i),
        poi_station_id=str(cfg.get("poi_station_id") or bundled.get("poi_station_id") or ""),
    )


class DwdWeatherProvider:
    def __init__(
        self,
        config: DwdConfig | None = None,
        *,
        warnings_client: DwdWarningsClient | None = None,
        observations_client: DwdObservationsClient | None = None,
    ) -> None:
        self._cfg = config or DwdConfig()
        self._warnings_client = warnings_client
        self._observations_client = observations_client
        self._initialized = False

    # --- lifecycle ------------------------------------------------------

    async def initialize(self) -> None:
        self._initialized = True

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="dwd", provider="dwd", instance_id=self._cfg.instance_id, mock=False
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            _CAPABILITY_BY_KEY[k] for k in self._cfg.enabled_capabilities if k in _CAPABILITY_BY_KEY
        )

    async def health(self) -> DiagnosticsReport:
        pending = [k for k in ("weather.radar",) if k in self._cfg.enabled_capabilities]
        return DiagnosticsReport(
            integration_id="dwd",
            state=HealthState.HEALTHY if self._initialized else HealthState.DISABLED,
            summary=(
                "warnings + observations live (E18-02/04)"
                + (f"; {', '.join(pending)} pending (E18-03)" if pending else "")
            ),
            checked_at=_dt.datetime.now(_dt.UTC),
            details={
                "region": self._cfg.region,
                "places": len(self._cfg.places),
                "warncells": len(self._cfg.warncell_ids()),
                "poi_stations": len(
                    {p.poi_station_id for p in self._cfg.places if p.poi_station_id}
                ),
                "enabled_capabilities": ", ".join(sorted(self._cfg.enabled_capabilities)),
                "attribution": ATTRIBUTION,
            },
        )

    async def shutdown(self) -> None:
        self._initialized = False

    # --- data --------------------------------------------------------

    async def get_warnings(self, *, region: str) -> list[dict[str, object]]:
        client = self._warnings_client or DwdWarningsClient(
            self._cfg.warnings.get("base_url") or DEFAULT_BASE_URL
        )
        warncells = self._cfg.warncell_ids() or None
        alerts = await asyncio.to_thread(client.fetch_alerts, warncell_ids=warncells)
        return [a.as_item() for a in alerts]

    async def get_observations(self, *, station_ids: list[str]) -> list[dict[str, object]]:
        """The latest reading per configured place that has a POI station. The
        ``station_ids`` argument is ignored — the adapter owns the place→station
        map (E18-06 passes ``[]``). A place without a station contributes nothing
        ("keine Daten")."""
        client = self._observations_client or DwdObservationsClient(
            self._cfg.observations.get("base_url") or _OBS_BASE_URL
        )
        targets = [(p.name, p.poi_station_id) for p in self._cfg.places if p.poi_station_id]
        return await asyncio.to_thread(_fetch_observations, client, targets)

    async def get_radar_frames(self, *, area: str) -> list[Any]:
        raise DwdNotImplementedError("get_radar_frames is E18-03 (DWD GeoServer WMS, ADR-0026)")


def _fetch_observations(
    client: DwdObservationsClient, targets: list[tuple[str, str]]
) -> list[dict[str, object]]:
    """Latest reading per (place, station). A single failing station is skipped;
    only an all-failure raises (E18-06 keeps the last good snapshot)."""
    from integrations.dwd.observations import DwdObservationsError

    out: list[dict[str, object]] = []
    failed_stations: set[str] = set()
    for place, station_id in targets:
        try:
            out.extend(o.as_item() for o in client.fetch(place=place, station_id=station_id))
        except DwdObservationsError:
            failed_stations.add(station_id)
    if failed_stations and failed_stations == {s for _, s in targets}:
        raise DwdObservationsError("every POI station fetch failed")
    return out


def _parse_config(raw: dict[str, Any] | None) -> DwdConfig:
    cfg = raw or {}
    place_cfgs = cfg.get("places") or []
    if place_cfgs:
        places = tuple(_place(p["name"], p) for p in place_cfgs)
    else:
        places = tuple(_place(name) for name in DEFAULT_PLACES)
    return DwdConfig(
        instance_id=cfg.get("instance_id", "dwd-1"),
        region=cfg.get("region", "mittelfranken"),
        enabled_capabilities=tuple(cfg.get("enabled_capabilities", tuple(_CAPABILITY_BY_KEY))),
        places=places,
        warnings=dict(cfg.get("warnings", {})),
        radar=dict(cfg.get("radar", {})),
        observations=dict(cfg.get("observations", {})),
    )


def build(config: dict[str, Any] | None = None) -> DwdWeatherProvider:
    """Manifest entry point — construct from validated config."""
    return DwdWeatherProvider(_parse_config(config))
