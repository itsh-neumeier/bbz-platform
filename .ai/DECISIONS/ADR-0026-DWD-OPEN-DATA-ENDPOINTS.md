# ADR-0026: DWD Open Data — which public services the `dwd` integration uses

## Status
Accepted (2026-09-01, review E18-01 / #375) · amended 2026-09-01 (E18-02 / #377 —
warnings feed changed COMMUNEUNION → **DISTRICT** after inspecting real samples;
see the note under Decision §1)

## Context
Epic 18 builds the first *real* live-integration reference: DWD weather warnings,
radar / precipitation, and local observations for Mittelfranken (MASTER_PROMPT
§10, §13.12). `integrations/dwd/README.md` and the `WeatherProvider` protocol
both say the concrete endpoints are **chosen by ADR at the start of Phase 7, not
guessed** — and the roadmap's rule 6 lists DWD among the APIs whose contract must
not be invented.

DWD publishes several overlapping open-data surfaces. They must be pinned before
E18-02…04 write clients, so the adapters are built against a decided contract and
recorded fixtures rather than assumptions.

All DWD open data is served over HTTPS, needs no credentials, and is licensed
under GeoNutzV / DL-DE-BY-2.0 (free use with source attribution "Deutscher
Wetterdienst").

## Decision
The `dwd` integration uses these three DWD Open Data services:

1. **Warnings → CAP 1.2 feed**
   `https://opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/` — Landkreis /
   kreisfreie-Stadt granularity (WARNCELLID prefix `1`), the operationally right
   level for a Leitstelle. **(E18-02 amendment:** the ADR first picked
   `COMMUNEUNION_DWD_STAT/` — recorded samples showed that is per-Gemeinde
   (WARNCELLID prefix `8`), far too fine for "warnings for Nürnberg";
   `DISTRICT_DWD_STAT/` is one row per Kreis/Stadt. COMMUNEUNION stays available
   via config `warnings.base_url` for a deployment that wants Gemeinde detail.)
   Files are ZIP archives of CAP 1.2 XML,
   `Z_CAP_C_EDZW_<UTC timestamp>_PVW_STATUS_PREMIUMDWD_DISTRICT_DE.zip`, the
   lexically-last is current, refreshed every ~10–15 min. The place → **warncell
   id** mapping is vendored in `integrations/dwd/data/mittelfranken.json` (built
   from `cap_warncellids.csv`), refreshed deliberately, not at runtime.
   Normalise each `(alert, de-DE info, area)` to `(region=areaDesc, type=event,
   level=severity 1–4, valid_from=onset, valid_to=expires (often absent),
   headline, description+instruction, source_ref=identifier, warncell_id)`.
   `msgType=Cancel` and geocode-less areas are dropped.

   **XML:** stdlib `ElementTree` (expat, no external-entity resolution), input
   size-capped; the fetch/unzip is stdlib `urllib`+`zipfile` run in a worker
   thread — **no new runtime dependency**. `defusedxml` / `httpx` can be swapped
   in later if the threat model or async needs tighten.

2. **Radar / precipitation → DWD GeoServer WMS**
   `https://maps.dwd.de/geoserver/dwd/wms` (layer `dwd:Niederschlagsradar` /
   the RV product), requested as rendered PNG frames clipped to a Mittelfranken
   bounding box, one per 5-minute radar step, each tagged with its UTC step time
   (ADR-0017). The raw RADOLAN/RADVOR binary composites under
   `https://opendata.dwd.de/weather/radar/` are **not** used in Phase 7 (they
   need a bespoke binary decoder); revisit if the WMS proves insufficient.

3. **Local observations → POI current-weather CSV**
   `https://opendata.dwd.de/weather/weather_reports/poi/` — one
   `<station_id>-BEOB.csv` per station (semicolon-separated, ~24 h of hourly
   values). The place → **POI station id** mapping is integration config
   (E18-01), seeded from the DWD station list. Normalise the latest row to
   `(station_id, place, observed_at, temperature_c, wind_speed_ms,
   precipitation_mm, …)`.

**What this ADR fixes:** the service per capability, the access pattern (poll +
cache, never a runtime dependency on DWD being up), the region/place → id mapping
living in config/vendored data, and UTC timestamps throughout. **What each
adapter epic finalises from recorded samples:** the exact field/column names and
parsing (CAP XML elements, WMS `GetCapabilities` layer/CRS, POI CSV header).

**Degradation contract (all three):** a fetch failure or a parse failure serves
the last good cached value and reports health `degraded` with `last_success_at`;
it never raises into the caller and never blocks a request. Empty/again-degraded
is a clear "no data", not an error. HA: the refresh is a leader-elected singleton
(ADR-0018 / E04-08); the cache is per node.

## Consequences
- Outbound HTTPS to `opendata.dwd.de` and `maps.dwd.de` only — added to the
  egress allowlist; no inbound, no credentials, no PII.
- `cap_warncellids.csv` and the POI station list are **vendored** into
  `integrations/dwd/data/` and updated by a deliberate PR, not fetched live — a
  DWD directory reshuffle can't silently break resolution.
- The WMS choice means radar frames are pre-rendered images, not data — fine for
  the §13.12 timeline; an "export the values under the cursor" feature would need
  the raw product later.
- Every DWD-derived view in the UI must carry the "Deutscher Wetterdienst"
  attribution (licence condition).

## Alternatives considered
- **`app-prod-ws.warnwetter.de/v30`** (the WarnWetter app's backend) — richer
  JSON, but undocumented, unversioned in practice, and explicitly an app
  backend, not an open-data contract. Rejected: it *is* the "invent the API"
  trap.
- **brightsky.dev** (third-party JSON-over-DWD) — clean API, but adds a
  third-party dependency and availability risk in front of a public source we
  can hit directly. Rejected for the reference integration; a deployment may
  still point config at a mirror.
- **Raw RADOLAN binary** for radar — most faithful, but a large decoder for no
  Phase-7 benefit over rendered WMS frames. Deferred.
