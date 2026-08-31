"""``dwd`` adapter — scaffold (roadmap E18-01).

A protocol-conformant :class:`~bbz_integration_sdk.providers.WeatherProvider`
that carries **no DWD client yet**. Lifecycle answers with safe values so the
core can register and health-check the provider; every *data* method raises
:class:`DwdNotImplementedError` until its adapter epic lands:

* :meth:`get_warnings` — E18-02 (CAP 1.2 feed, ADR-0026)
* :meth:`get_radar_frames` — E18-03 (GeoServer WMS, ADR-0026)
* :meth:`get_observations` — E18-04 (POI CSV, ADR-0026)

Only outbound HTTPS to ``opendata.dwd.de`` / ``maps.dwd.de``; no credentials, no
PII (ADR-0026). Every DWD-derived value carries the "Deutscher Wetterdienst"
attribution (licence condition).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

from bbz_integration_sdk.capabilities import Capability, CapabilitySet
from bbz_integration_sdk.diagnostics import DiagnosticsReport, HealthState
from bbz_integration_sdk.providers.base import ProviderInfo

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
    """A DWD data method was called before its adapter epic (E18-02..04) landed."""


@dataclass(frozen=True)
class DwdPlace:
    name: str
    warncell_id: str = ""
    poi_station_id: str = ""


@dataclass
class DwdConfig:
    instance_id: str = "dwd-1"
    region: str = "mittelfranken"
    enabled_capabilities: tuple[str, ...] = tuple(_CAPABILITY_BY_KEY)
    places: tuple[DwdPlace, ...] = field(
        default_factory=lambda: tuple(DwdPlace(name=n) for n in DEFAULT_PLACES)
    )
    warnings: dict[str, Any] = field(default_factory=dict)
    radar: dict[str, Any] = field(default_factory=dict)
    observations: dict[str, Any] = field(default_factory=dict)


class DwdWeatherProvider:
    """Scaffold DWD weather provider — lifecycle only (E18-01)."""

    def __init__(self, config: DwdConfig | None = None) -> None:
        self._cfg = config or DwdConfig()
        self._initialized = False

    # --- lifecycle ------------------------------------------------------

    async def initialize(self) -> None:
        self._initialized = True

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            integration_id="dwd",
            provider="dwd",
            instance_id=self._cfg.instance_id,
            mock=False,
        )

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet(
            _CAPABILITY_BY_KEY[k] for k in self._cfg.enabled_capabilities if k in _CAPABILITY_BY_KEY
        )

    async def health(self) -> DiagnosticsReport:
        return DiagnosticsReport(
            integration_id="dwd",
            state=HealthState.UNKNOWN if self._initialized else HealthState.DISABLED,
            summary="DWD client not implemented yet (E18-02..04); scaffold only",
            checked_at=_dt.datetime.now(_dt.UTC),
            details={
                "region": self._cfg.region,
                "places": len(self._cfg.places),
                "enabled_capabilities": ", ".join(sorted(self._cfg.enabled_capabilities)),
                "attribution": ATTRIBUTION,
            },
        )

    async def shutdown(self) -> None:
        self._initialized = False

    # --- data (WeatherProvider) — E18-02..04 ---------------------------

    async def get_warnings(self, *, region: str) -> list[Any]:
        raise DwdNotImplementedError("get_warnings is E18-02 (DWD CAP feed, ADR-0026)")

    async def get_observations(self, *, station_ids: list[str]) -> list[Any]:
        raise DwdNotImplementedError("get_observations is E18-04 (DWD POI CSV, ADR-0026)")

    async def get_radar_frames(self, *, area: str) -> list[Any]:
        raise DwdNotImplementedError("get_radar_frames is E18-03 (DWD GeoServer WMS, ADR-0026)")


def _parse_config(raw: dict[str, Any] | None) -> DwdConfig:
    cfg = raw or {}
    places = tuple(
        DwdPlace(
            name=p["name"],
            warncell_id=str(p.get("warncell_id", "")),
            poi_station_id=str(p.get("poi_station_id", "")),
        )
        for p in cfg.get("places", [])
    ) or tuple(DwdPlace(name=n) for n in DEFAULT_PLACES)
    enabled = tuple(cfg.get("enabled_capabilities", tuple(_CAPABILITY_BY_KEY)))
    return DwdConfig(
        instance_id=cfg.get("instance_id", "dwd-1"),
        region=cfg.get("region", "mittelfranken"),
        enabled_capabilities=enabled,
        places=places,
        warnings=dict(cfg.get("warnings", {})),
        radar=dict(cfg.get("radar", {})),
        observations=dict(cfg.get("observations", {})),
    )


def build(config: dict[str, Any] | None = None) -> DwdWeatherProvider:
    """Manifest entry point — construct from validated config."""
    return DwdWeatherProvider(_parse_config(config))
