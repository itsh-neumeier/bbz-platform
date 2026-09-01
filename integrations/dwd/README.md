# dwd — DWD Weather integration

The first *real* live-integration reference (MASTER_PROMPT §10, §13.12): DWD
weather **warnings**, **radar / precipitation**, and **local observations** for
Mittelfranken, feeding the Wetterlage page, the radar timeline, the operational
assessment, and "create a BBZ event from a warning".

## Status

| Capability | DWD service (ADR-0026) | Epic | State |
|---|---|---|---|
| `weather.warnings` | CAP 1.2 **DISTRICT** feed `opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/` | E18-02 | **live** |
| `weather.observations` | POI CSV `opendata.dwd.de/weather/weather_reports/poi/` (`<station>-BEOB.csv`) | E18-04 | **live** |
| `weather.radar` | GeoServer WMS `maps.dwd.de/geoserver/dwd/wms` (`Radar_rv_product_1x1km_ger`) | E18-03 | **live** |

**Observations** (`observations.py`): `parse_poi_csv` reads the 3-header
semicolon CSV (latin-1, decimal comma, `---` = missing) and normalises the newest
row's temperature / humidity / wind / precipitation / pressure / cloud-cover to
the E18-06 contract. `DwdWeatherProvider.get_observations` fetches one CSV per
configured place that has a `poi_station_id`; a place without one contributes
nothing ("keine Daten"), a single failing station is skipped, all-fail raises.

**Warnings** (`warnings.py`): `DwdWarningsClient` fetches the lexically-last
`…_DISTRICT_DE.zip`, `parse_cap_alerts` turns each `(alert, de-DE info, area)`
into a normalized dict (region, type, level 1–4 from `severity`, valid_from/to,
headline, description+instruction, source_ref, warncell_id); `msgType=Cancel` and
geocode-less areas drop out. The adapter filters to the configured places'
warncells and runs the blocking fetch in a worker thread. Fetch/parse failure →
`DwdWarningsError` (E18-06 keeps the last-good snapshot).

**Radar** (`radar.py`): `parse_time_dimension` reads the layer's ISO8601 `time`
dimension (`<start>/<end>/PT5M`) from a stdlib-`ElementTree` GetCapabilities
parse; `build_frames` turns `(latest, step)` into the last `frame_count` (default
12) **GetMap URLs**, oldest → newest, clipped to the Mittelfranken bbox
(`crs=CRS:84`, `image/png`, transparent). We do **not** proxy the images — a frame
is a ready URL the browser fetches from DWD directly. `get_radar_frames` runs the
blocking GetCapabilities read in a worker thread; the E18-06 refresh puts the
series in the per-node `weather_read.RADAR_CACHE` and E18-07 serves it. A WMS
outage raises `DwdRadarError` → the refresh keeps the last frames + health
`degraded`.

## Config

- `region` — operational label (default `mittelfranken`), also the radar clip.
- `places[]` — `{name, warncell_id?, warncell_ids?, poi_station_id?}`. A name in
  `data/mittelfranken.json` (Nürnberg / Fürth / Erlangen / Schwabach / Ansbach /
  Neustadt a.d. Aisch) resolves its DISTRICT warncells automatically; the fields
  override / extend that (e.g. a place outside Mittelfranken).
- `enabled_capabilities` — activate warnings / radar / observations independently.
- `warnings.base_url` — override the CAP feed (e.g. to COMMUNEUNION for Gemeinde
  granularity); `observations.base_url` — override the POI base.
- `radar` — `{wms_url?, layer?, bbox?: [minLon,minLat,maxLon,maxLat], frame_count?}`
  (defaults: the RV composite layer, the Mittelfranken bbox, 12 frames).

## Rules

- DWD open data is **public and documented** — no invention (ADR-0026 pins the
  services). Parsing is verified against **recorded fixtures**
  (`tests/fixtures/cap_district/real_*.xml` are real DWD alerts, polygons
  stripped). CI never touches the network.
- Outbound HTTPS to `opendata.dwd.de` / `maps.dwd.de` only. No credentials, no PII.
  No new runtime dependency — stdlib `urllib` / `zipfile` / `ElementTree`.
- Degradation: a fetch/parse failure raises (`DwdWarningsError` /
  `DwdObservationsError` / `DwdRadarError`); the E18-06 refresh singleton keeps the
  last good snapshot / radar frames and marks health `degraded` / `stale`.
- The refresh is a leader-elected singleton (ADR-0018); the cache is per node. The
  radar series is replaced wholesale each tick, so it is bounded to `frame_count`.
- Every DWD-derived view must carry the **"Deutscher Wetterdienst"** attribution
  (GeoNutzV / DL-DE-BY-2.0 licence condition).
