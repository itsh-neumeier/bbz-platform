# Metrics

`GET /api/v1/system/metrics` — Prometheus exposition of the **HA-relevant**
gauges (roadmap E06-13, MASTER_PROMPT §23). Requires `system.cluster.view`; it
is **not** a public endpoint. A dedicated internal-only scrape port and the
full app/runtime metric set are Epic 22.

Scrape each node separately — the values are per-node and comparing them
(e.g. `bbz_event_seq_head`) is how you see a lagging follower.

| metric | type | meaning |
|---|---|---|
| `bbz_cluster_dcs_healthy` | gauge 0/1 | this node can reach at least one etcd endpoint |
| `bbz_cluster_quorum` | gauge 0/1 | an etcd raft leader is visible (the cluster can make progress) |
| `bbz_cluster_node_is_primary{node}` | gauge 0/1 | that node currently holds the PostgreSQL primary |
| `bbz_replication_lag_bytes{node}` | gauge | standby replay lag in bytes (0 on the primary / when caught up) |
| `bbz_event_seq_head` | gauge | highest applied `domain_events.event_seq` **on this node** |
| `bbz_outbox_pending` | gauge | `external_action_outbox` rows still awaiting dispatch |
| `bbz_worker_leader{singleton}` | gauge 0/1 | this node holds the etcd lease for that cluster singleton |
| `bbz_stream_connections{transport}` | gauge | open event-stream connections on this node (`transport` = `sse` \| `ws`) |

## What to alert on (starting points — tuned in Epic 22)

- `bbz_cluster_quorum == 0` for > 30 s — the cluster cannot fail over.
- `bbz_cluster_dcs_healthy == 0` on a node — that node lost etcd.
- `sum(bbz_cluster_node_is_primary) != 1` — zero or two primaries (split brain).
- `bbz_replication_lag_bytes > 1048576` (the `maximum_lag_on_failover`, ADR-0021)
  sustained — a failover here would drop data.
- `bbz_outbox_pending` climbing without draining — the dispatcher singleton is
  stuck or unelected.
- `delta(bbz_event_seq_head)` diverging between nodes — replication is behind.
