# ADR-0011: Event Log + State Tables, with Outbox/Inbox

## Status
Accepted (2026-08-29, review E01-01 / #20)

## Context
MASTER_PROMPT §3/§16 require a global monotonic `event_seq`, catch-up by sequence
(not timestamp), idempotent commands, and active/active exactly-once side effects
(ADR-0004/0006). We must decide whether to use full event sourcing or a
transactional state model plus an append-only event log.

## Decision
- **Not** full event sourcing. Use authoritative relational state tables **plus**
  an append-only `domain_events` / `audit_events` log written in the *same*
  transaction as the state change.
- `event_seq` is a `BIGINT` sequence/identity on the **PostgreSQL primary only**
  (single writer → strictly monotonic; gaps tolerated, order guaranteed).
- `commands` table stores the idempotency key + result hash for dedupe/replay.
- **Transactional outbox** for external side effects (telephony control, camera
  open, notifications) — dispatched by a worker, idempotent on
  `provider_event_id + rule_version + action_index`.
- **Provider-event inbox** for inbound external events (alarms, calls) —
  deduplicated before any trigger/rule evaluation.
- Clients catch up via `GET /api/v1/.../stream?after_seq=N` then live stream.

## Consequences
- Simpler queries and onboarding than event sourcing; still fully auditable and
  replay-safe.
- Discipline required: every state mutation must also append its event in-tx.

## Alternatives considered
Full event sourcing (rejected: heavier read model, projection rebuild burden,
overkill for this domain); Kafka/log broker as system of record (rejected:
another stateful cluster next to Patroni, and cross-store transactionality pain).
