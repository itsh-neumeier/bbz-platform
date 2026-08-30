# Runbook: database failover

Patroni-managed PostgreSQL failover for the 2+1 topology (ADR-0001, ADR-0018).
Replication mode: **synchronous with automatic fallback** (ADR-0021) —
`deploy/node/patroni/patroni.node.yml`.

## Targets

| | Value | Source |
|--|--|--|
| Detection + promotion | ≈ 30–45 s | `ttl: 30`, `loop_wait: 10` |
| **RTO** (writable again, incl. app reconnect) | ≤ 60 s | ADR-0021 |
| **RPO**, both DB nodes healthy | 0 | `synchronous_mode: true` |
| **RPO**, degraded (standby down) window | ≤ `maximum_lag_on_failover` (1 MiB) | ADR-0021 |

## Expected automatic behaviour

- Patroni detects primary loss, promotes the synchronous standby, and updates
  the leader key under `/patroni` in etcd.
- App nodes stay up; in-flight writes briefly fail with `503`/`409` and clients
  retry with the same `command_id` (idempotent — ADR-0012).
- If the **standby** (not the primary) fails, the primary drops it from
  `synchronous_standby_names` and keeps accepting writes in **async** mode.
  This is logged and shows in `patronictl list` / `/cluster/status`; it is not
  an outage, but durability is reduced until the standby returns.
- The cluster observer writes a `DB_FAILOVER` audit event on any leader change
  (E06-04 / E06-07).

## Operator checks

1. etcd quorum intact (3 members: SRV01, SRV02, QUORUM01) — `etcdctl endpoint status`.
2. `patronictl -c /etc/patroni.node.yml list` — one `Leader`, one `Sync Standby`
   (or `Replica` while degraded), no `Sync Standby` missing for long.
3. New primary accepting writes; old primary rejoins as standby and catches up
   via WAL + `pg_rewind` (no manual base backup — ADR-0001).
4. Replication lag returns to ~0 and the standby is back to `Sync Standby`
   before declaring healthy.
5. CUCM `CONTROL_LEADER` lease still held by a live node; if it moved, confirm a
   `TELEPHONY_RECONCILED` audit was written (ADR-0002).

## If quorum is lost (witness + one node down)

- The cluster goes **read-only** to avoid split brain. Do not force-promote.
- Restore a third voting etcd member (`deploy/quorum` or a re-added node), let
  Patroni re-elect, then verify writes and lag as above.

## Manual switchover (planned maintenance)

```
patronictl -c /etc/patroni.node.yml switchover bbz --candidate <standby-name>
```

Take the node out of the reverse-proxy pool first; put it back once it reports
`Sync Standby`.
