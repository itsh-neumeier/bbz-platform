# Coding conventions

Binding. `.ai/RULES.md` and the ADRs win over anything here.

## Module boundaries (enforced by `import-linter`)

- `bbz_core.domain` imports nothing else in `bbz_core` and never
  `bbz_integration_sdk`. It defines its own interfaces (dependency inversion).
- Only `bbz_core.integrations_host` imports `bbz_integration_sdk`.
- `bbz_core` never imports anything under `integrations/`.
- Concrete integrations never import each other; `telephony_sip` must not depend
  on Cisco/JTAPI or `telephony_cucm`.

## API / commands

- Base path `/api/v1`. See ADR-0012 for the command envelope, error body,
  409-on-conflict and idempotency rules.
- Every write is idempotent on `command_id`. Every critical state change writes
  an audit event in the same transaction (ADR-0011).
- Permissions checked server-side, always. Never frontend-only.

## Events & time

- Ordering / catch-up / conflict resolution use `event_seq`, never timestamps.
- All instants are UTC in storage and payloads (ADR-0017).
- Event envelope shape: `packages/event-schemas` — bump `schema_version` on
  changes; additive within a major.

## Database migrations — expand / contract (zero-downtime)

Rolling updates (MASTER_PROMPT §21) run **old and new app code against the same
schema at the same time**. Every migration must therefore be safe for the
**previous** app version. Split any breaking change across releases:

| phase | migration does | app release |
|---|---|---|
| **expand** | add nullable column / new table / new index (`CONCURRENTLY` in prod) / **add** a CHECK as `NOT VALID` then `VALIDATE` | release N — new code writes both old + new shape, reads either |
| **migrate-data** | backfill, in batches, idempotent | release N (or a job) |
| **contract** | drop the old column / table / constraint; add `NOT NULL`; rename | release N+1 — only after every node runs N |

**Never in one migration:** `DROP COLUMN` / `DROP TABLE` / `RENAME` / `ALTER
COLUMN … SET NOT NULL` / dropping a NOT-NULL or unique constraint that old code
relies on — unless it is the *contract* step and the matching *expand* shipped
in a prior release.

Mark the phase in the migration's module docstring so CI and reviewers can
see intent:

```
"""events.legacy_ref: drop the pre-0042 column

expand-contract: contract   (expand was 0042_events_new_ref, released in vX)
"""
```

`expand-contract: safe` marks a genuinely non-breaking alter (e.g. widening a
`VARCHAR`, adding a default). `server/tests/test_migration_safety.py` fails on a
destructive op without one of these markers; the `migration-compat` CI job runs
the newest schema against the **previous** app version.

### Migration review checklist

- [ ] Reversible (`downgrade()` restores the prior schema).
- [ ] Named constraints (`ck_%(table)s_%(name)s`, `uq_…`, `fk_…`).
- [ ] `revision` string == filename stem; `down_revision` is the current head.
- [ ] New enum-like column = `VARCHAR(n)` + named `CheckConstraint` (not a PG enum).
- [ ] DDL triggers/functions also created by an `after_create` hook on the model
      (so `create_all` in tests matches).
- [ ] Expand/contract phase marked; a contract references its expand.
- [ ] Big-table changes note `CONCURRENTLY` / batching for the operator.
- [ ] `alembic upgrade head && downgrade base && upgrade head` green (CI does this).

## Naming

- Python: `snake_case`; packages `bbz_*`. Vue components `PascalCase`; stores
  `useXStore`. Integration ids `lower_snake` (`telephony_cucm`, `coda_video`).
- Branches: `feature|fix|refactor|docs/<issue>-<short-name>`.
- Commits: Conventional Commits.

## Vendor integrations

- Never invent an external API. If docs are missing, the integration stays a
  placeholder + mock and the gap is listed in `.ai/CURRENT_STATE.md`.
- Vendor payloads are normalized at the integration edge; the core only sees
  BBZ-defined normalized events.

## Accessibility

- Functional requirement. Keyboard path for every operable control; respect
  `prefers-reduced-motion`; a11y lint at error level.

## Secrets

- Nothing sensitive in the repo. Config via `BBZ_`-prefixed env; secrets via the
  orchestrator/secret store. Never log DTMF codes or key material (ADR-0015).
