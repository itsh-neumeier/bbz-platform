# DWD test fixtures — provenance

All fixtures are **recorded once** and committed so the adapter tests are
deterministic and network-free (roadmap E18-10, ADR-0026). Captured 2026-09-01
via the `bbz-e14-deps` container (which has internet); see
`.claude` memory `dwd-adapter-notes` for the capture method.

## `cap_district/` — DWD CAP 1.2 warnings

Feed: `opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/` (Landkreis /
kreisfreie-Stadt granularity, WARNCELLID prefix `1`).

| file | origin | notes |
|---|---|---|
| `real_sturmboeen_alert.xml` | real DWD alert | `msgType=Alert`, severity `Moderate` → level 2; single area; has `<onset>`/`<expires>` |
| `real_boeen_update_a.xml` / `_b.xml` | real DWD alerts | `msgType=Update`; multi-area |
| `real_boeen_seewetter.xml` | real DWD alert | `msgType=Update`, **no `<expires>`** — `valid_to` stays `None` |
| `mittelfranken_multi_area.xml` | **synthetic** | one alert over Nürnberg / Fürth / Passau — exercises the warncell filter; source_ref ends `mittelfranken-fixture.DEU` |
| `cancelled.xml` | **synthetic** | `msgType=Cancel` → parses to `[]` |

Only the CAP elements the adapter reads are kept; `<polygon>` / `<circle>`
coordinate blobs (tens of KB each) are stripped — the adapter never reads
geometry, only `area/geocode[valueName=WARNCELLID]`.

## `poi/` — DWD POI current-weather CSV

Feed: `opendata.dwd.de/weather/weather_reports/poi/<station>-BEOB.csv`
(semicolon, latin-1, decimal comma, `---` = missing, newest row first).

| file | station | notes |
|---|---|---|
| `10763-BEOB.csv` | 10763 (Nürnberg) | real; 3 header rows + 5 data rows (newest `01.09.26 03:00 UTC`) |
| `10761-BEOB.csv` | 10761 | real; `---` in several columns → `value=None` |

## `wms/` — DWD GeoServer WMS `GetCapabilities`

Service: `maps.dwd.de/geoserver/dwd/wms`, layer `Radar_rv_product_1x1km_ger`
(RV composite, 5-minute steps).

| file | notes |
|---|---|
| `getcapabilities_radar.xml` | real, trimmed to the RV layer + `RADOLAN-RW` (a 10-minute layer, for the step-parse test) |
| `getcapabilities_no_time.xml` | derived — the RV layer with **no** `<Dimension name="time">` (only `REFERENCE_TIME`) → `parse_time_dimension` raises |
