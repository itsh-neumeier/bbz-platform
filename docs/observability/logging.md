# Structured logging

Roadmap **E22-03** (builds on E04-09 correlation ids and E22-01 traces).
`bbz_core.logging`.

## Format

One JSON object per line (outside `BBZ_ENVIRONMENT=local`, which uses a colour
console renderer). Every line carries:

| field | always | meaning |
|---|---|---|
| `timestamp` | ✓ | ISO-8601, UTC (ADR-0017) |
| `level` | ✓ | `debug` … `critical` |
| `event` | ✓ | the log message (a short stable string, not a sentence) |
| `logger` | ✓ | the module (`bbz_core.infra.leader`) |
| `node_id` | ✓ | `BBZ_NODE_ID` |
| `correlation_id` | in a request | E04-09 — the `x-correlation-id` |
| `trace_id` / `span_id` | tracing on, in a span | E22-01 |
| `user_id` | authenticated request | set by `current_auth` |

`correlation_id` / `user_id` are `contextvars` reset per request by
`CorrelationIdMiddleware`; `trace_id` comes from the active OpenTelemetry span.

## Redaction — two layers, both before the renderer

1. **By key** (`_redact_keys`) — a value whose key contains `password`, `passwd`,
   `secret`, `token`, `authorization`, `api_key`, `private_key`, `credential`,
   `dtmf`, `otp`, `recovery_code`, `session_key` is replaced with `[redacted]`,
   recursively through nested dicts/lists. So `log.info("x", headers=req.headers)`
   cannot leak an `Authorization` header.
2. **By value** (`_redact`) — any transient secret registered with
   `bbz_core.redaction.redacting(...)` (E17-06) is masked by substring, so a
   DTMF code a provider echoes into an error message never reaches a log line.

No log entry contains a secret — enforced by `test_logging.py`.

## Configuration (all `BBZ_`-prefixed)

| setting | default | effect |
|---|---|---|
| `BBZ_LOG_LEVEL` | `INFO` | the root level |
| `BBZ_LOG_JSON` | `true` | JSON vs console renderer |
| `BBZ_LOG_LEVELS` | `""` | per-module overrides — `bbz_core.auth=WARNING,bbz_core.infra.leader=DEBUG`. Longest matching prefix wins. The coarse gate drops to the lowest configured level so a per-module `DEBUG` actually reaches the pipeline. |
| `BBZ_LOG_SAMPLE` | `""` | drop a fraction of a noisy event — `heartbeat=0.01,cluster_status_probe=0.1` (keep-ratio; `0` drops it entirely). Keyed on the `event` string. |
| `BBZ_LOG_FILE` | `""` | also append every JSON line to this file. A sidecar / logrotate ships and truncates it — **E22-03 runs no log backend**. Empty = stdout only. |

## Shipping

stdout is the transport (12-factor). `BBZ_LOG_FILE` is the hand-off point for an
external shipper (Vector, Fluent Bit, Promtail, …). An HTTP / syslog shipper
would plug in as another `_Tee` sink in `configure_logging`.

## Not in scope

Operating a log store / search backend; log-based alerting (that is metrics —
E22-06); per-request access logs (the OTel server span + this line already
cover it).
