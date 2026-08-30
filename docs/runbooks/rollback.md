# Runbook: rollback

Code / config / deploy rollback. For a **restore from backup** after a state
store is lost, see `restore.md`.

## Code / config

- Every change lands via PR. Revert = `git revert <merge-commit>`; redeploy the
  previous immutable image digest.
- No force-push to `main`; releases are tagged and immutable.

## Application deploy

- Redeploy the previous digest on the affected node, health-gate, then the other
  node (reverse of `rolling-update.md`).
- Risky domain behavior sits behind feature flags → disable without redeploy.

## Database

- Migrations are expand/migrate/contract and N-1 compatible, so a code rollback
  needs **no** schema rollback in the normal case.
- `alembic downgrade` only for non-destructive steps; CI verifies
  `upgrade → downgrade → upgrade`.
- Destructive "contract" steps ship one release *after* the expand, once the
  rollback window has closed. If a contract step must be undone, roll **forward**
  with a corrective migration; never a data-losing downgrade.
- Before any risky migration: a fresh base backup (`deploy/backup/pg-backup.sh`)
  and note the WAL position, so a PITR to just before the migration is possible
  (`restore.md`).

## Integrations

- A misbehaving integration is disabled via `integrations.enable_disable` (or set
  to mock mode), not a full redeploy.

## Agents / kiosk

- Staged by workplace group; previous signed package retained; agents keep
  working against either server across a version rollback.
