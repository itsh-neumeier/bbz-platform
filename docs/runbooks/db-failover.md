# Runbook: database failover

> Stub — real content in Phase 2 (Patroni + etcd, ADR-0001/0018).

## Expected automatic behavior

- Patroni detects primary loss, promotes the synchronous standby, updates the
  leader key in etcd.
- App nodes stay up; writes briefly fail with `503`/`409` and clients retry with
  the same `command_id` (idempotent — ADR-0012).
- `/cluster/status` reflects the new roles once Phase 2 wires it.

## Operator checks

1. etcd quorum intact (3 members: SRV01, SRV02, QUORUM01).
2. New primary accepting writes; old primary rejoins as standby and catches up
   via WAL (no manual data copy — ADR-0001).
3. Replication lag returns to normal before declaring healthy.
4. CUCM `CONTROL_LEADER` lease still held by a live node; if it moved, confirm a
   `TELEPHONY_RECONCILED` audit was written (ADR-0002).

## If quorum is lost (witness + one node down)

- Cluster goes read-only to avoid split brain. Restore a third voting member
  before promoting anything manually.
