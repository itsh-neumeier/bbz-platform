# ADR-0020: Audit / event-log immutability

## Status
Proposed

## Context
MASTER_PROMPT §17/§26.7 requires that audit entries — and by extension the
append-only `domain_events` log (ADR-0011) — cannot be altered or deleted after
the fact. `.ai/CURRENT_STATE.md` tracks this as an open point: "audit immutability
mechanism (append-only + DB grants / hash-chain / WORM)".

The application already refuses UPDATE/DELETE at the ORM layer (E04-01), but that
only binds code that goes through the ORM. A `psql` session, a bug that issues
raw SQL, or a compromised service account would bypass it. We need enforcement in
the database itself, and it must survive `pytest` (schema built from
`Base.metadata`) as well as Alembic-migrated databases, and replicate with the
data.

Postgres GRANT/REVOKE does not help when the application connects as the table
owner (owners keep all privileges). A least-privilege role is worth doing in
production but is deployment-specific and not sufficient on its own.

## Decision
`audit_events` and `domain_events` are made append-only by a **`BEFORE UPDATE OR
DELETE` trigger** that unconditionally `RAISE EXCEPTION`. The trigger function
(`bbz_forbid_row_mutation`) and its triggers are created:

* by a SQLAlchemy `after_create` DDL hook on both tables, so every
  `Base.metadata.create_all` (tests, fresh dev DB) has them; and
* by migration `0016_audit_immutability` for already-provisioned databases.

Production deployments additionally run the application under a role that has
only `INSERT, SELECT` on these tables (documented in the deploy runbook, E24) —
defence in depth, not the primary control.

A cryptographic hash-chain (`prev_hash` / `row_hash`) is **not** adopted now:
the trigger already gives tamper-*prevention*; a hash-chain only adds tamper-
*evidence* against someone who can also disable triggers (i.e. a full DB
compromise), and it complicates inserts and retention. It stays a candidate for
a future ADR if an external compliance requirement demands detectability.

## Consequences
* Any UPDATE/DELETE on `audit_events` / `domain_events` fails with a clear
  error, from any client, in every environment.
* Corrections are additive only: a wrong audit row is followed by a
  compensating row, never edited.
* `DROP TABLE` (DDL) still works, so Alembic downgrades and the test-teardown
  `drop_all` are unaffected.
* Retention/pruning of these tables, if ever needed, must be done by a
  privileged maintenance path that drops+recreates or detaches partitions —
  not row DELETEs. None is needed in Phase 1.

## Alternatives considered
* **GRANT/REVOKE only** — bypassed by the owner role; deployment-specific.
* **Hash-chain / WORM storage** — heavier, only adds detection, deferred.
* **Rely on the ORM guard** — does not bind raw SQL or other clients.
