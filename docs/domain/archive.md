# Archive & post-processing — data model

*Roadmap Epic 20 (E20-01). Related: ADR-0011 (append-only event log + outbox/inbox),
`.ai/FEATURES.md` (archive view + post-processing notes), permission `events.view`.*

## Decision: a view over `events` + history, **not** an `event_archive` table

An archived event is an ordinary `events` row whose `status` is `archived`.
Archiving is a **status transition**, not a move:

- it appends one `event_status_history` row (`… → archived`),
- it writes one `EVENT_ARCHIVED` audit entry in the same transaction,
- it appends one domain event to `domain_events`.

Nothing is copied, summarised, or deleted. Reactivation (`events.reactivate`,
`confirm=true` + reason) is the symmetric transition back.

We therefore do **not** introduce a separate `event_archive` / snapshot table.
Rationale:

| Option | Why not |
|---|---|
| `event_archive` table populated on archive | Duplicates the source of truth; risks drift; a bug in the copy step silently loses history; "no data reduction on archiving" (E20-01) is easier to guarantee when there is nothing to reduce. |
| Snapshot JSON blob per archived event | Same drift risk; freezes a shape that keeps evolving (calls arrive in Epic 11); not queryable. |
| **View / aggregator query over the live tables** ✅ | All backing tables are already append-only or never hard-deleted (ADR-0011, audit immutability, `workflow_*` runtime). An archived event's detail is computed by the **same** reads as an active one. |

## The aggregator

`bbz_core.infra.repositories.archive_queries.ArchiveQueryRepository.detail(event_id)`
returns an `ArchiveDetail` regardless of the event's status:

- `detail` — core fields, description, full status history, all notes
  (`EventQueryRepository.detail`);
- `domain_events` — the ordered `domain_events` log for the aggregate;
- `workflows` — every `workflow_instances` row for the event, each with its
  `workflow_task_results` and `workflow_decisions`, plus the pinned template
  key / name / version;
- `audit_refs` — `audit_events` rows targeting the event
  (`target_type = 'event'`);
- `calls` — reserved for Epic 11 (telephony); currently always empty.

Exposed as `GET /api/v1/events/{event_id}/archive-detail` (`events.view`, no
audit — it is a read). The UI lands in E07-11 (#113).

## Invariant under test

`server/tests/test_archive_detail.py` archives an event and asserts the
archive-detail bundle has the **same depth** (identical status history, notes,
domain events, workflow results, and *more* audit refs) as it did while active —
archiving only ever *adds* rows.
