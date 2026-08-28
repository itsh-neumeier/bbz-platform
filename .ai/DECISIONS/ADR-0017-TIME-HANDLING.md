# ADR-0017: Time Handling

## Status
Proposed

## Context
MASTER_PROMPT §3: timestamps are for display/audit, never the replication cursor
(that is `event_seq`). Events carry both `occurred_at_utc` and
`occurred_at_local`.

## Decision
- Store and transmit all instants in **UTC** (`timestamptz`, ISO-8601 with `Z`).
- Compute a display-local timestamp using a configured site timezone
  (`Europe/Berlin` default; per-site override allowed since scopes include
  `region`/`bbz`/`workplace`).
- Never derive ordering, catch-up, or conflict resolution from timestamps —
  always `event_seq` / WAL position.
- Client clocks are untrusted; offline commands record `client_timestamp` for
  forensics only, server assigns authoritative time and sequence on ingest.

## Consequences
- No DST/skew bugs in ordering or dedupe.
- A small amount of tz conversion logic at the presentation edge.

## Alternatives considered
Local-time storage (rejected: DST ambiguity, cross-site inconsistency).
