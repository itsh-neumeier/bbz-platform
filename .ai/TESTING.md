# .ai/TESTING.md

Required test levels:
- unit
- integration
- API
- authorization
- frontend
- E2E
- HA/failover
- recovery/catch-up
- migration/rollback

Critical flows:
- event ownership
- archive/reactivation
- call documentation
- contact priorities
- failover
- client reconnect


Additional critical tests:
- BKU Agent enrollment and workplace binding
- agent failover SRV01 -> SRV02
- allowlisted web-app launch
- arbitrary URL/shell command rejection
- remote logout/restart confirmation + authorization + audit
- duplicate command replay rejection
- Siedle ring -> technical endpoint match -> Cayuga action -> BBZ popup
- door-open -> call connect -> DTMF -> automatic hangup (exactly once)
- duplicate Cisco call event does not trigger a second unlock
- BMA technical number creates exactly one event and binds workflow version
- EPK AND split/join
- EPK XOR split/join
- EPK OR split/join
- workflow publish validation and version pinning
- monitor routing change reflected on the provider + audited
- monitor lower-left output stays BBZ-OS (server-enforced)
- monitor standard-layout reset
- monitor layout profile save + apply


## HA failure-scenario harness (E06-11)

`deploy/ha-test/` brings up a single-host mini HA cluster (2 app nodes, a
Patroni primary/standby behind HAProxy, a 3-member etcd, a Caddy LB) and runs
seven repeatable scenarios via `deploy/ha-test/run.sh`:

- `srv01-down`, `srv02-down` — an app server is lost; the LB keeps serving,
  writes continue, the returning node catches up.
- `db-primary-loss` — the PostgreSQL primary is killed; Patroni promotes the
  standby within the RTO (ADR-0021); `event_seq` never regresses.
- `net-isolation` — one server is network-isolated; the other keeps quorum and
  serves; the isolated node never becomes a second primary.
- `witness-down` — the etcd witness is lost; 2/3 quorum keeps the cluster
  writable.
- `client-reconnect` — a streaming client's node dies; it reconnects to the
  other node with its last `event_seq` and gets a gap-free continuation
  (E06-07).
- `recovery` — a full cluster restart converges to one primary and loses
  nothing.

`assert_single_primary` runs after every fault — **two Patroni leaders is
always a failure** (split brain). CI: `.github/workflows/ha-nightly.yml`
(scheduled, non-gating until shaken out on real hardware).


## DWD weather integration (E18-10)

The `dwd` adapter (ADR-0026) is tested **only against recorded fixtures** — the
PR CI never touches `opendata.dwd.de` / `maps.dwd.de`.

**Fixtures** (`integrations/dwd/tests/fixtures/`, provenance in its `README.md`):

| dir | content |
|---|---|
| `cap_district/` | 4 real DWD CAP-1.2 alerts (polygons stripped) + 2 synthetic (Mittelfranken multi-area filter, a `Cancel`) |
| `poi/` | 2 real POI `-BEOB.csv` (trimmed to 5 rows) |
| `wms/` | a trimmed real WMS `GetCapabilities` + a variant with no usable `time` dimension |

**Coverage:**

- **Parsing / normalisation** — `test_dwd_warnings.py`, `test_dwd_observations.py`,
  `test_dwd_radar.py`: each fixture → the E18-06 item contract; CAP severity →
  level, missing `expires`, multi-area = one row per area, `Cancel` → nothing;
  POI decimal comma / `---` = missing / newest row; WMS `time` dimension →
  `(latest, step)` → GetMap URL series clipped to the bbox.
- **Degraded paths** — `test_dwd_degraded.py`: corrupt zip, feed listing without a
  DISTRICT zip, a truncated CAP member, a non-German-only alert, an all-`---` POI
  row, an unparseable timestamp, a thin CSV, `GetCapabilities` without a `time`
  dimension or without our layer → each raises the adapter's typed error or
  returns a thin-but-valid list, never a bare crash.
- **No network** — `test_dwd_no_network.py`: an autouse fixture makes
  `urllib.request.urlopen` raise; every adapter still parses its fixture end to
  end over a stub transport.
- **Cache / health / recovery** — `server/tests/test_weather_refresh.py`: a failed
  kind → `degraded` (keeps last data) / `down` (never succeeded); past the TTL →
  `stale`; the next good refresh → back to `ok` with `last_error` cleared;
  `overall` = the worst kind; a failed radar refresh keeps the cached frame
  series. `test_weather_api.py` serves the cached series with the health block.
