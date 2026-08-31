# ADR-0024: Trigger execution via a leader-elected drain worker

## Status
Accepted (2026-08-31, review E15-15 / #333)

## Context
E15-04 normalises every inbound provider event (telephony, alarm, door, panic)
into an `inbound_signal.v1` and E15-09 built `TriggerEngine` to match it against
the published trigger rules and run the actions exactly once. But nothing in
production actually *drives* the engine — `TriggerEngine.process_inbox_event` and
`resume_unprocessed` were only called from tests and the E15-11 simulation
endpoint. The telephony ingest route (E11-03) feeds only the call lifecycle.

Something has to turn "a signal landed in the provider inbox" into "the engine
ran". Two shapes were on the table: run the engine synchronously inside the
ingest request, or queue the signal and let a background worker process it. The
exactly-once ledger (`trigger_executions`), the inbox `processed_at` flag and
`resume_unprocessed` were all designed for the queued shape.

## Decision
- A normalized inbound signal is persisted as its **own** `provider_event_inbox`
  row via `record_inbound_signal` (E15-04), separate from any raw-event row the
  same external event also creates (e.g. the telephony call-lifecycle row). The
  signal row's `dedupe_key` is `signal:<raw dedupe key>`; it starts unprocessed.
- The telephony ingest path (`ingest_telephony_event`), on a **new** event, maps
  it with `from_telephony_event` and — if it yields a signal — queues that signal
  row. A mapping/queueing failure is logged and swallowed: it must never fail
  call ingestion.
- A new leader-elected cluster singleton **`trigger-engine`** (ADR-0018 lease,
  alongside `outbox-dispatcher` / `workflow-timer`) ticks
  `TriggerEngine(session).resume_unprocessed()` — it drains unprocessed signal
  rows, runs each through the engine, and marks them processed. Exactly-once is
  the `trigger_executions` UNIQUE key, unchanged.
- `TriggerEngine.process_inbox_event` skips a row whose `normalized` is not an
  inbound signal (`signal_type` absent) — the raw telephony rows are inert to it.

Ingestion stays fast and cannot be broken by a rule; a crash or failover between
"signal queued" and "engine ran" is recovered by the next tick, without
duplicates.

## Consequences
- One more background singleton to run and monitor; `/cluster/status` gains a
  `trigger-engine` leader.
- A short, bounded delay (one tick, ~2 s) between a signal arriving and its
  actions firing — acceptable for event creation / notification; automatic door
  opening (Epic 17) will need its own latency review and may add a synchronous
  fast-path then.
- One external event can produce two inbox rows (raw + signal). The inbox is a
  generic arrival ledger, so this is consistent; the dedupe keys keep them
  distinct and each idempotent.

## Alternatives considered
**Synchronous in the ingest request** — lowest latency, but a slow or failing
rule now degrades or breaks ingestion, and a crash mid-sequence still needs the
worker as a fallback, so it is strictly more code for a latency win we do not yet
need. Revisit for Epic 17 door opening.
**Reuse the raw telephony inbox row** (no second row) — would entangle the call
lifecycle's and the trigger engine's `processed_at` tracking on one row, and the
row's `normalized` is the raw event, not the signal the engine wants.
