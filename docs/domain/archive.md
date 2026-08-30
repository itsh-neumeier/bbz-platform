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

Exposed as `GET /api/v1/events/{event_id}/archive-detail` (E20-03; `events.view`,
no audit — it is a read). Every list inside the bundle is ordered deterministically
(`event_seq`, then timestamps ascending). The UI lands in E07-11 (#113).

## Listing the archive

`GET /api/v1/events` (E03-12) is the chronological list *including* archived
events — the backing query for the archive view. E20-02 adds filters, all
optional and composable, without changing the keyset-cursor contract
(`(created_at, id)` descending):

| query param | meaning |
|---|---|
| `created_from`, `created_to` | creation-time bounds (ISO 8601; no offset ⇒ UTC, ADR-0017) |
| `priority` (repeatable) | OR-set of `low`/`medium`/`high`/`critical` |
| `bbz_id` | exact BBZ scope match |
| `assignee_id` | the *active* responsible user |
| `status` | exact status (e.g. `archived`) |

`queue=active` still returns the live work queue and never contains archived
events; it ignores these filters.

## Post-processing notes (E20-04)

Notes are **append-only and versioned**:

- `POST /api/v1/events/{id}/notes` (`events.postprocess`) takes
  `kind ∈ {work, postprocess}`; a `postprocess` note can be added to an archived
  event.
- `PATCH /api/v1/events/{id}/notes/{note_id}` (`events.postprocess`) *edits* a
  note by writing a new `event_notes` row (`version` + 1, same `thread_id`) and
  setting `superseded_by_id` on the previous row — old text is never lost. The
  path locks the current tip (`FOR UPDATE`); `note_id` may be any version in the
  thread.
- `GET /api/v1/events/{id}/notes` (`events.view`) lists each thread's current
  version plus its ordered `history` of superseded versions.
- The plain event detail and the archive-detail bundle show **only the current
  version** of each note.

Add and edit each emit a domain event (`EVENT_NOTE_ADDED` / `EVENT_NOTE_UPDATED`)
and an audit entry (both are `CRITICAL_ACTIONS`).

## Reactivation — two-step, guarded (E20-05)

Reactivating an archived event is deliberately two requests:

1. `POST /api/v1/events/{id}/reactivation-intent` (`events.reactivate`) — returns
   a short-lived, single-purpose **token** (stateless HMAC over
   `event_id · user_id · version · expiry`, keyed with the app secret; TTL
   `reactivation_token_ttl_seconds`, default 300). 409 if the event is not
   archived. Not audited.
2. `POST /api/v1/events/{id}/reactivate` — requires `confirm: true`, a non-empty
   `reason`, **and** that `token`. The token is rejected (422) unless it was
   minted for this event, this caller, and the current `version`
   (`X-Expected-Version`). On success the event goes `archived → opened`, so it
   is back in `queue=active`; `EVENT_REACTIVATED` is a mandatory audit with the
   reason.

**Accidental-series guard:** a second reactivation of the same event within
`reactivation_cooldown_seconds` (default 60) is refused with **429**. Set the
setting to `0` to disable.

## Invariant under test

`server/tests/test_archive_detail.py` (the aggregator query) and
`server/tests/test_archive_detail_api.py` (the endpoint) archive an event and
assert the archive-detail bundle has the **same depth** (identical status
history, notes, domain events, workflow results, and *more* audit refs) as it did
while active — archiving only ever *adds* rows.
