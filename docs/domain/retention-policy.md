# Data retention policy

*Roadmap E20-07. Sources: MASTER_PROMPT §17 (Nachvollziehbarkeit), §26.7
("keine archivierten Ereignisse hart löschen"). Related: ADR-0011 (append-only
event log), ADR-0020 (audit immutability). WORM storage is Epic 23, out of
scope here.*

## Principle

The **operational record is kept forever.** Archiving an event is a status
transition, not a deletion (see `archive.md`). Nothing that documents *what
happened* — an event, its history, its workflow, its audit trail — is ever
hard-deleted by the application or by an operator action.

Only **derived or non-essential** data has a retention window, and only where a
shorter lifetime is harmless or required (storage, privacy of incidental data).

## Never pruned — no retention window applies

| Table | Guard |
|---|---|
| `events` | `events_no_delete` BEFORE DELETE trigger (migration 0023) + no app delete path |
| `event_status_history` | `event_status_history_no_delete` trigger (0023) |
| `event_notes` (all versions) | `event_notes_no_delete` trigger (0023); edits *append*, never overwrite (E20-04) |
| `domain_events` | `domain_events_append_only` BEFORE UPDATE OR DELETE trigger (0016) |
| `audit_events` | `audit_events_append_only` trigger (0016) + `AuditImmutableError` ORM guard (E04-01) |
| `workflow_instances` / `workflow_tokens` / `workflow_task_results` / `workflow_decisions` | no app delete path; retained with their event |
| `event_assignments` | ownership history — reassigned by flipping `active`, never deleted |

The triggers block a `DELETE` from **any** client (psql, a migration, a stray
ORM call), not just the application. `DROP TABLE` (DDL, e.g. a test teardown)
is deliberately unaffected.

## May be pruned — derived / non-essential

Housekeeping jobs (Epic 22) prune these past a configurable age. They carry no
independent evidentiary value — the durable record is the domain-event log and
the audit trail.

| Table | Setting | Default | What it is |
|---|---|---|---|
| `commands` (completed) | `retention_completed_command_days` | 30 | idempotency replay cache; window ≥ the longest offline-client replay gap |
| `commands` (stale pending) | — (`purge_stale`, age-based) | — | abandoned in-flight command rows |
| `external_action_outbox` (done) | `retention_completed_outbox_days` | 90 | dispatched side-effect rows; the fact is in `domain_events` |
| `provider_event_inbox` (processed) | `retention_processed_inbox_days` | 90 | inbound dedupe rows; the resulting event/call is the record |
| radar frames, camera stills, raw telemetry | per-source (Epic 16 ff.) | — | reconstructable / high-volume; the event keeps the decision, not every frame |
| metrics samples | Prometheus retention | — | operational, not domain data |

A retention window of `0`/unset for a *derived* class means "keep until
housekeeping decides"; for the never-pruned classes a window is meaningless and
none is defined.

## Enforcement

`server/tests/test_no_hard_delete.py` (contract test) fails if:

- any `bbz_core` module gains a `DELETE` against `events`, `event_status_history`,
  `event_notes`, `domain_events`, or `audit_events` (ORM `delete(<Model>)` or raw
  SQL);
- any migration `upgrade()` drops one of those tables or issues a `DELETE FROM`
  against it;
- migration 0016 or 0023 stops creating its guard triggers.
