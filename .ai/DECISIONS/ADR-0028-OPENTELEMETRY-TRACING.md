# ADR-0028: OpenTelemetry tracing — activating the no-op seam

## Status
Accepted (2026-09-01, review E22-01 / #447)

## Context
`bbz_core.telemetry.instrument_app` has been a documented no-op since the
foundation phase — ADR-0008 lists "OpenTelemetry prepared (no-op seam)" and
MASTER_PROMPT §6 requires OTel to be *prepared*. E22-01 (Epic 22) turns the seam
into real tracing and is the dependency of E22-03 (structured-log pipeline) and
E22-07 (collector + dashboards).

Requirements from the roadmap:
- one request produces one connected trace API → DB → Outbox;
- `trace_id` appears in the structured log;
- the exporter is switchable on/off **by configuration, not code**;
- no sensitive data in span attributes (redaction).

Constraints from the rest of the platform:
- `filterwarnings = ["error"]` in the pytest config — a library that warns on
  import or use breaks the suite;
- `bbz_core.infra.db.get_engine` is `@lru_cache` and binds
  `create_async_engine` by name (`from sqlalchemy.ext.asyncio import …`), which
  the OTel instrumentor's module-level patch cannot see;
- `redaction.py` doctrine (E17-06): *every* sink runs `scrub()`;
- ADR-0017: timestamps are UTC; ADR-0015: all config via `BBZ_`-prefixed env.

## Decision

**Dependencies.** Add `opentelemetry-api`, `opentelemetry-sdk`,
`opentelemetry-exporter-otlp-proto-http`, and the FastAPI / SQLAlchemy / httpx
instrumentation packages to `server` (6 direct + ~12 transitive incl.
`protobuf`, `requests`, `wrapt`). Core packages pin `>=1.44,<2`; the
instrumentation packages are permanently beta-versioned upstream (`0.NbM`) but
production-used and hard-pin their peers, so `>=0.65b0,<1`.

**Exporter: OTLP over HTTP/protobuf, not gRPC.** `-proto-http` pulls only
`requests`; `-proto-grpc` would pull `grpcio`, a heavy native wheel. A collector
accepts both.

**Config surface: `BBZ_`-prefixed settings only.** We do **not** read the
standard `OTEL_*` env vars — one config surface (ADR-0015). `otel_enabled`
(default **true**), `otel_traces_exporter` (`none` | `otlp`, default `none`),
`otel_exporter_otlp_endpoint`, `otel_exporter_otlp_headers`,
`otel_traces_sampler_ratio` (default `1.0`).

**Tracing on by default, exporter off by default.** With no exporter, spans are
created, sampled, and dropped — the cost is negligible and `trace_id` is
available to logs in every environment. Shipping spans is the opt-in: set
`BBZ_OTEL_TRACES_EXPORTER=otlp` + an endpoint. No code change (AC). The test
suite runs with `BBZ_OTEL_ENABLED=false` (process-wide instrumentation would
otherwise leak between tests); `test_otel_tracing.py` opts in.

**Instrumentation.**
- FastAPI — per app (`FastAPIInstrumentor.instrument_app`), so building many
  apps in one test process is safe. ASGI `receive`/`send` spans suppressed.
- httpx — process-wide (`HTTPXClientInstrumentor`).
- SQLAlchemy — **per engine**, wired from `get_engine()` via
  `telemetry.instrument_engine(engine)`. The instrumentor's global
  `create_async_engine` patch does not reach `db.py`'s name binding, so each
  engine gets an `EngineTracer` directly (idempotent per engine). This also
  covers the test fixture that clears the engine cache each test.

**Sampling.** `ParentBased(TraceIdRatioBased(ratio))` — honour an inbound
`traceparent` decision, otherwise sample at `ratio` (default: everything; free
while the exporter is off). W3C `traceparent` is the propagation format in and
out.

**`correlation_id` ↔ `trace_id`.** The correlation-id middleware stamps
`bbz.correlation_id` on the active server span; `bbz_core.logging` adds
`trace_id` / `span_id` (hex) to every log line emitted inside a span. Given a
log line you can find the trace and vice versa.

**Redaction.** Primary control: we add exactly one attribute we control
(`bbz.correlation_id`, run through `scrub()`), and instrumentation is configured
to capture no request/response headers or bodies — `db.statement` is the
parameterised SQL, never bound values. Defense-in-depth: the exporter is wrapped
so every span (attributes **and** event attributes, e.g. `exception.message`)
passes through `bbz_core.redaction.scrub` before it leaves the process.

**Supersedes** the "no-op seam" note in ADR-0008 for tracing. The
metrics/Prometheus half of §23 stays as delivered in E06-13 and is extended by
E22-02.

## Consequences
- One connected trace per request across FastAPI → SQLAlchemy → the outbox
  INSERT, with `trace_id` in the logs — the debugging story §23 asks for.
- New runtime dependency footprint (largest single add in the project). Audited
  by `pip-audit --strict` on every PR; versions locked as a coordinated set.
- `telemetry.py` is no longer import-cheap-and-inert, but stays a no-op at
  runtime unless `otel_enabled`; the SDK is imported lazily inside
  `configure_tracing`.
- A collector to receive OTLP is **not** in scope (E22-07); until then the
  exporter stays `none` and tracing is local-only.
- Adding header/body capture later, or a new `OTEL_*` passthrough, is an ADR
  touch here.

## Alternatives considered
- **gRPC OTLP exporter.** Rejected — `grpcio` native build, no benefit for our
  scale.
- **Standard `OTEL_*` env vars / `opentelemetry-instrument` auto-loader.**
  Rejected — a second config surface next to `BBZ_` settings; the auto-loader
  also fights the app factory.
- **Tracing off by default.** Rejected — then `trace_id` is absent from logs
  everywhere by default, and E22-03 depends on it. On-with-no-exporter is free.
- **Redact via a `SpanProcessor.on_end` hook.** Rejected — `ReadableSpan`
  attributes are immutable at end; the exporter wrapper rebuilds the span
  instead, which also reaches event attributes.
- **Global `SQLAlchemyInstrumentor().instrument()`.** Insufficient — misses
  `db.py`'s `from … import create_async_engine` binding; per-engine wiring is
  explicit and order-independent.
