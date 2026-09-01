# Distributed tracing (OpenTelemetry)

Roadmap **E22-01**, decision **ADR-0028**. Turns the `bbz_core.telemetry`
no-op seam into real OpenTelemetry tracing.

## What you get

- **One connected trace per request**: the FastAPI server span, every
  SQLAlchemy statement it runs (including the `external_action_outbox` INSERT),
  and any outbound `httpx` call — all under one `trace_id`, parent-linked.
- **`trace_id` in the logs**: every structured log line emitted inside a request
  carries `trace_id` and `span_id` (see `bbz_core/logging.py`). Given a log
  line you can jump to the trace; given a trace you have the `correlation_id`.
- **`correlation_id` on the trace**: the request's `x-correlation-id` (E04-09)
  is stamped on the server span as `bbz.correlation_id`.

## Configuration

All `BBZ_`-prefixed (ADR-0015). We deliberately do **not** read the standard
`OTEL_*` env vars.

| setting | default | meaning |
|---|---|---|
| `BBZ_OTEL_ENABLED` | `true` | create spans at all. Off ⇒ the seam is fully inert. |
| `BBZ_OTEL_TRACES_EXPORTER` | `none` | `none` keeps spans in-process; `otlp` ships them. |
| `BBZ_OTEL_EXPORTER_OTLP_ENDPOINT` | `""` | collector base URL, e.g. `http://otel-collector:4318` (`/v1/traces` is appended). |
| `BBZ_OTEL_EXPORTER_OTLP_HEADERS` | `""` | extra OTLP headers, `key=value,key2=value2`. |
| `BBZ_OTEL_TRACES_SAMPLER_RATIO` | `1.0` | head-sampling ratio when there is no inbound `traceparent` decision. |

**Turning the exporter on is config only, never a code change** (roadmap AC):

```sh
BBZ_OTEL_TRACES_EXPORTER=otlp
BBZ_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

With `BBZ_OTEL_TRACES_EXPORTER=none` (the default until a collector is
deployed — E22-07) spans are still created and sampled, so `trace_id` shows up
in logs, but nothing leaves the process.

## Propagation

W3C `traceparent` in and out. An inbound `traceparent` is honoured
(`ParentBased` sampler); outbound `httpx` requests carry one so a downstream
service joins the same trace.

## What is captured — and what is not

Captured span attributes: HTTP method / route / status / peer; `db.system` /
`db.name` / `db.operation` / `db.statement`; our `bbz.correlation_id`.

**`db.statement` is the parameterised SQL** — `... WHERE id = $1`, never the
bound values. Request/response **headers and bodies are not captured** (they may
carry tokens or DTMF codes). As a defense-in-depth net the span exporter runs
`bbz_core.redaction.scrub` over every span — attributes and event attributes
(e.g. `exception.message`) — so a transient secret registered with
`redacting(...)` (E17-06) never leaves the process even if some instrumentation
picks it up. See ADR-0028 for the full redaction rationale.

## Code seam

`bbz_core/telemetry.py`:

- `instrument_app(app)` — called once from `create_app()`. Builds the
  `TracerProvider`, instruments httpx process-wide and FastAPI per-app.
- `instrument_engine(engine)` — called from `bbz_core.infra.db.get_engine()`
  for each engine (the instrumentor's global `create_async_engine` patch cannot
  see `db.py`'s name binding).
- `record_correlation_id(cid)` — called from the correlation-id middleware.
- `shutdown_tracing()` — flushes on app shutdown (lifespan).

## Not in scope here

- The OTel **collector** deployment + Grafana dashboards + SLO docs — E22-07.
- The structured-log **shipping** pipeline + per-module levels — E22-03
  (depends on this issue).
- Prometheus **metrics** — E06-13 (`docs/metrics.md`) + E22-02.
