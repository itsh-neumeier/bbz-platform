# Metrics

`GET /api/v1/system/metrics` — Prometheus exposition of the per-node metric set
(roadmap E06-13 + **E22-02**, MASTER_PROMPT §23). Requires `system.cluster.view`;
it is **not** a public endpoint. A dedicated internal-only scrape port + Grafana
dashboards are E22-07.

Scrape each node separately — the values are per-node and comparing them
(e.g. `bbz_event_seq_head`) is how you see a lagging follower.

## HA / cluster (E06-13)

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

## Application / §23 (E22-02)

| metric | type | meaning |
|---|---|---|
| `bbz_http_request_duration_seconds{method,route,status}` | histogram | request latency. `route` is the **template** (`/api/v1/events/{event_id}`), rebuilt from the path with its params folded back; an unrouted request is `route="unmatched"`. `_count` / `_sum` / `_bucket` as usual. |
| `bbz_db_pool_connections{state}` | gauge | SQLAlchemy async pool connections — `state` = `in_use` \| `idle` \| `overflow` (0 on a `NullPool` deploy) |
| `bbz_connected_clients` | gauge | active sessions (not revoked, not expired) — one per logged-in client |
| `bbz_commands_pending` | gauge | accepted commands with no result yet (a client that submitted offline and has not synced the outcome) |
| `bbz_call_lines{state}` | gauge | telephony lines by `state` (`in_service` \| `out_of_service` \| `unknown`) |
| `bbz_calls_active` | gauge | calls not in a terminal state (`disconnected` / `failed` do not count; `ended_pending_documentation` does — it is still open work) |
| `bbz_integration_health{domain,integration}` | gauge | health of an integration **loaded in this process**: `1` healthy / `0.5` degraded / `0` unavailable\|unknown / `-1` disabled. Cross-integration aggregation + persistence is E22-05. |

### Cardinality

`route` is bounded by the route table; `status` by the HTTP status codes actually
returned; `method` by the verbs actually used. `bbz_call_lines{state}` and
`bbz_integration_health` use small closed label sets. No metric carries a
user id, path id, or free text.

## What to alert on (starting points — E22-06 makes these real rules)

- `bbz_cluster_quorum == 0` for > 30 s — the cluster cannot fail over.
- `bbz_cluster_dcs_healthy == 0` on a node — that node lost etcd.
- `sum(bbz_cluster_node_is_primary) != 1` — zero or two primaries (split brain).
- `bbz_replication_lag_bytes > 1048576` (the `maximum_lag_on_failover`, ADR-0021)
  sustained — a failover here would drop data.
- `bbz_outbox_pending` climbing without draining — the dispatcher singleton is
  stuck or unelected.
- `delta(bbz_event_seq_head)` diverging between nodes — replication is behind.
- `histogram_quantile(0.95, rate(bbz_http_request_duration_seconds_bucket[5m]))`
  rising — API latency regression.
- `bbz_db_pool_connections{state="in_use"}` pinned at the pool ceiling — DB
  saturation / a leak.
- `bbz_commands_pending` climbing — offline clients not reconnecting, or a stuck
  command path.
- `bbz_integration_health < 1` for a core integration — telephony / monitor down.
