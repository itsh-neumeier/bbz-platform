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

## OpenTelemetry tracing (E22-01)

Tracing is **process-wide** once armed, so the suite runs with
`BBZ_OTEL_ENABLED=false` (`conftest.py` sets the default) and only
`server/tests/test_otel_tracing.py` opts in — a module-scoped fixture arms
tracing with an in-memory span exporter behind the real
`redaction`-wrapping exporter, and `telemetry._reset_for_tests()` tears it down.

Coverage:

- **connected trace** — a takeover request (`API → DB → outbox INSERT`) produces
  exactly one SERVER span; every DB span shares its `trace_id` and hangs off the
  request; `external_action_outbox` appears in the captured `db.statement`s;
  `bbz.correlation_id` on the server span equals the request's `X-Correlation-Id`.
- **`trace_id` in logs** — the `_add_trace_context` structlog processor stamps
  `trace_id` / `span_id` on a line emitted inside a span, and neither field once
  the span has ended.
- **config-only exporter toggle** — `_build_exporter` returns `None` for
  `otel_traces_exporter="none"` and an `OTLPSpanExporter` for `"otlp"`; no code
  path differs.
- **redaction** — a span attribute + an `exception` event carrying a
  `redacting(...)`-registered secret come out masked after export.
- **clean no-op** — `configure_tracing(Settings(otel_enabled=False))` is `False`
  and `current_trace_ids()` is `None`.

## Rate limiting (E23-04)

`test_rate_limiting.py` (5): `POST /auth/login` past `BBZ_RATE_LIMIT_LOGIN`
(set to `3/60`) → `429` + numeric `Retry-After` + a `RATE_LIMIT_TRIGGERED` audit
row carrying the rule but not the attempted password; the counter is **shared**
across two httpx clients (same DB bucket) — the 4th hit from either is blocked;
`0/60` disables the rule; a `2/1` window lets requests through again after a
1.2 s sleep; `/auth/totp/activate` is throttled per user (`2/60` → the 3rd/4th
are `429`). The `db` fixture drops `rate_limit_hits` per test.

## Runtime secrets (E23-01)

`test_secret_store.py` (9): `EnvFileSecretProvider` — env beats file, the TTL
cache and `invalidate()`; `BBZ_SECRET_PROVIDER=vault` raises with an ADR-0019
pointer; `verify_required_secrets` is a no-op in `ci` but raises
`SecretsIncompleteError` in `production` on a dev `jwt_secret` / a passwordless
DSN; `POST /api/v1/system/secrets/reload` needs `system.cluster.manage`; a
mounted `$BBZ_SECRETS_DIR/bbz_door_dtmf_encryption_key` file rewritten then
`reload`ed → `{"reloaded": ["door_dtmf_encryption_key"]}`, `get_settings()` sees
the new value, one `SECRET_ROTATED` audit row (name only, no value).
`monkeypatch.setitem(Settings.model_config, "secrets_dir", …)` because
`secrets_dir` is bound at import.

## Observability stack (E22-07)

`test_monitoring_stack.py` (8): the collector / Prometheus / Grafana config
files parse and wire together (collector traces pipeline complete, Prometheus
loads `bbz.rules.yml` and scrapes the gated `/api/v1/system/metrics`, the
datasource `uid` matches); **every dashboard panel's `target.expr` references a
`bbz_` metric that `bbz_core.infra.metrics.REGISTRY` actually exports** (histogram
`_bucket`/`_count`/`_sum` suffixes stripped). CI also runs
`docker compose --profile monitoring config -q`, `promtool check config` and the
collector's own `validate`.

## Alert rules (E22-06)

`deploy/monitoring/alerts/bbz.rules.test.yml` — `promtool test rules`, run in the
CI `docker compose config` job (`prom/prometheus:v3.1.0`). 8 cases drive one
rule's expression past / below its threshold and assert the alert fires (with the
exact rendered labels + annotations) or stays silent. `promtool check rules` on
`bbz.rules.yml` gates rule validity.

## Integration health (E22-05)

`test_integration_health_api.py` (5): `GET /api/v1/integrations/health` needs
`integrations.diagnostics` (401 / 403 without); it lists every active
integration with a normalised `state` and a set `checked_at`; a probe that
raises makes that integration `down` and bumps `consecutive_errors` on each
call; `last_activity_at` picks up a `provider_event_inbox` row keyed by the
integration id; the `integration-health` singleton tick returns an `int` and
fills the table. `BBZ_WEATHER_INTEGRATION_ID=none` keeps the DWD probe off the
network.

## `/health/details` (E22-04)

`test_health.py` — `/health/details` needs `system.cluster.view` (401 without a
session); with it, the body has `build.{version,revision,built_at}` and a
`checks[]` matrix (`database` / `cluster` / `dcs`) each with a numeric
`duration_ms`; patching the DB probe to fail flips that check's `ok` to `false`
with a `detail`, and the endpoint still returns `200`.

## Structured logging (E22-03)

`server/tests/test_logging.py` (8) reconfigures `configure_logging(stream=buf)`
and asserts the rendered JSON:

- **baseline fields** — `timestamp` / `level` / `event` / `logger` / `node_id`
  on every line; `correlation_id` / `user_id` only when the contextvars are set.
- **redaction** — a sensitive **key** (`password`, `refresh_token`, `dtmf_*`,
  a nested `Authorization` header) → `[redacted]`; a non-sensitive sibling
  untouched; a registered `redacting()` secret still scrubbed by value.
- **per-module levels** — `bbz_core.chatty=WARNING` drops its `info`, keeps its
  `warning`, leaves another module alone; a longer prefix beats a broader one.
- **sampling** — `heartbeat=0` drops every `heartbeat` line, keeps the rest.
- **file sink** — `BBZ_LOG_FILE` gets the same JSON lines as stdout.

## Prometheus metrics (E22-02)

`server/tests/test_metrics.py` covers the full §23 set at
`GET /api/v1/system/metrics`:

- **gated** — 401 without a session, 403 without `system.cluster.view`.
- **all §23 names present** — the E06-13 HA gauges + the E22-02 additions.
- **latency label is the template** — a request to `/api/v1/events/<uuid>`
  records under `route="/api/v1/events/{event_id}"`; the raw id never appears.
- **gauges track state** — login bumps `bbz_connected_clients`; an in-flight
  `commands` row bumps `bbz_commands_pending`; a `Line` / `Call` row moves
  `bbz_call_lines{state}` / `bbz_calls_active` (a `disconnected` call does not);
  a loaded mock provider shows `bbz_integration_health … 1.0`.
