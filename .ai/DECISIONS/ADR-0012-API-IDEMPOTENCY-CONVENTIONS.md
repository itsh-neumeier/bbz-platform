# ADR-0012: API and Idempotency Conventions

## Status
Accepted (2026-08-29, review E01-01 / #20)

## Context
MASTER_PROMPT §15/§16 fix the broad shape (REST + WebSocket/SSE, command_id,
optimistic concurrency, HTTP 409). The exact envelope and error contract must be
standardized before endpoints multiply.

## Decision
- Versioned base path `/api/v1`. Breaking changes → `/api/v2`, both served during
  migration.
- Every **write** carries a command envelope (headers in Phase 0,
  `bbz_core.api.idempotency.CommandEnvelope`): `X-Command-Id` (UUID, required),
  `X-Expected-Version` (int, required except creates), `X-Client-Id`,
  `X-Workplace-Id`, `X-Correlation-Id`, `X-Offline`.
- Uniform error body: `{"error": {"code", "message", "details?", "correlation_id"}}`.
- Concurrency conflict → `409` with the current server version in `details`.
- Duplicate `command_id` → the original result is returned, not re-executed.
- All responses echo `X-Correlation-Id` (generated if absent).
- Timestamps are UTC in payloads (ADR-0017); ordering is by `event_seq`, never
  by time.

## Consequences
- Clients (web, kiosk, agents) share one generic write/error path and one
  retry/idempotency story that survives failover.

## Alternatives considered
Per-endpoint ad-hoc payloads (rejected: no consistent retry/replay handling);
RFC 7807 `application/problem+json` (compatible in spirit; we keep a thinner
in-house envelope with `correlation_id` first-class).
