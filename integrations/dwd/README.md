# dwd — DWD Weather integration

The first *real* live-integration reference (MASTER_PROMPT §10, §13.12): DWD
weather **warnings**, **radar / precipitation**, and **local observations** for
Mittelfranken, feeding the Wetterlage page, the radar timeline, the operational
assessment, and "create a BBZ event from a warning".

## Status — scaffold (E18-01)

Manifest + config schema + a protocol-conformant `WeatherProvider` stub. The
`get_warnings` / `get_radar_frames` / `get_observations` methods raise
`DwdNotImplementedError` until their adapter epics land.

| Capability | DWD service (ADR-0026) | Epic |
|---|---|---|
| `weather.warnings` | CAP 1.2 feed `opendata.dwd.de/weather/alerts/cap/COMMUNEUNION_DWD_STAT/` + `cap_warncellids.csv` | E18-02 |
| `weather.radar` | GeoServer WMS `maps.dwd.de/geoserver/dwd/wms` (`dwd:Niederschlagsradar`) | E18-03 |
| `weather.observations` | POI CSV `opendata.dwd.de/weather/weather_reports/poi/` (`<station>-BEOB.csv`) | E18-04 |

## Config

- `region` — operational target (default `mittelfranken`), used for labelling and the radar clip.
- `places[]` — `{name, warncell_id, poi_station_id}`. Target places: Nürnberg,
  Fürth, Erlangen, Schwabach, Ansbach, Neustadt a.d. Aisch. The ids are looked up
  from the vendored DWD reference data (added with E18-02 / E18-04); empty until then.
- `enabled_capabilities` — activate warnings / radar / observations independently.
- `warnings` / `radar` / `observations` — per-service base URL, layer/bbox, refresh interval.

## Rules

- DWD open data is **public and documented** — no invention (ADR-0026 pins the
  exact services). The concrete field/column parsing is finalised per adapter
  epic from **recorded fixtures**, never assumptions.
- Outbound HTTPS to `opendata.dwd.de` / `maps.dwd.de` only. No credentials, no PII.
- Degradation: a fetch/parse failure serves the last good cached value and reports
  health `degraded` — it never raises into the caller and never blocks a request.
- The refresh is a leader-elected singleton (ADR-0018); the cache is per node.
- Every DWD-derived view must carry the **"Deutscher Wetterdienst"** attribution
  (GeoNutzV / DL-DE-BY-2.0 licence condition).
