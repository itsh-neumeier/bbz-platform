# Service levels — "what does healthy mean"

Roadmap **E22-07**. Target SLOs per core component and the signals that say a
component is green. Numbers are starting targets — tune per site once there is a
baseline. Metrics: `docs/metrics.md`; alert rules: `deploy/monitoring/`;
runbooks: `docs/runbooks/`.

The overriding rule (MASTER_PROMPT): **the Leitstelle keeps taking calls**. Every
SLO below is subordinate to that — a degraded observability stack, a lagging
standby or a down integration must never stop event and call handling.

---

## API

| | target | signal | breach |
|---|---|---|---|
| Availability | 99.9% / 30d | `bbz_http_request_duration_seconds_count{status!~"5.."}` ratio | `BbzApiErrorRateHigh` (>5% 5xx, 10m) |
| Latency p95 | < 500 ms (read), < 1 s (write) | `histogram_quantile(0.95, …bbz_http_request_duration_seconds_bucket…)` | `BbzApiLatencyHigh` (>1 s, 10m) |
| Correlation | every request has `correlation_id` + (tracing on) `trace_id` in its logs | `docs/observability/{logging,tracing}.md` | — |

**Green:** p95 under target, 5xx under 1%, `bbz_db_pool_connections{state="overflow"} == 0`.

## Database / replication (ADR-0021)

| | target | signal | breach |
|---|---|---|---|
| RPO | 0 while both DB nodes healthy (synchronous) | Patroni `synchronous_standby_names` populated | lone primary → degrades to async, logged |
| RTO | ≤ 60 s automatic failover | `docs/runbooks/db-failover.md` | — |
| Replication lag | < 1 MiB (`maximum_lag_on_failover`) | `bbz_replication_lag_bytes` | `BbzReplicationLagHigh` (5m) |
| Primary count | exactly 1 | `sum(bbz_cluster_node_is_primary)` | `BbzSplitBrain` (1m) |

**Green:** one primary, lag ~0, `bbz_cluster_quorum == 1`, `bbz_cluster_dcs_healthy == 1` on every node.

## Cluster / DCS

| | target | signal | breach |
|---|---|---|---|
| Quorum | always present | `bbz_cluster_quorum` | `BbzQuorumLost` (2m, critical) |
| Every singleton has a leader | yes | `sum by (singleton) (bbz_worker_leader)` == 1 each | `BbzWorkerLeaderMissing` (5m) |
| Failover of a singleton | < 2 × `worker_leader_ttl_seconds` (~20 s) | audit `WORKER_LEADER_CHANGED` | — |

## Event / command pipeline

| | target | signal | breach |
|---|---|---|---|
| Durability | no loss — append-only `domain_events` / `audit_events` (DB triggers, ADR-0020) | `test_replay_consistency.py` | — |
| Outbox dispatch | drains continuously; each side effect exactly once | `bbz_outbox_pending` flat/low | `BbzOutboxBacklog` (>100, 10m) |
| Offline-command sync | clients reconcile within the replay window | `bbz_commands_pending` | `BbzOfflineCommandsPending` (>50, 15m) |
| Client catch-up | a reconnecting client replays from `event_seq` with no gap/dup | `docs/client-catchup.md` | — |

## Telephony

| | target | signal | breach |
|---|---|---|---|
| No duplicate calls | a replayed provider event processes once | `provider_event_inbox` dedupe (E11-03) | — |
| Call documentation | every ended call gets a category before it closes | the E11-10 hangup guard | — |
| Line visibility | `bbz_call_lines{state}` reflects the provider | `bbz_integration_health{domain="telephony"}` | `BbzIntegrationDown` |

## Integrations

| | target | signal | breach |
|---|---|---|---|
| Health freshness | re-probed ≤ every 60 s | `integration_health.checked_at` (E22-05) | stale ⇒ singleton not running |
| Core integrations up | telephony + monitor `ok` | `bbz_integration_health` | `BbzIntegrationDown` / `BbzIntegrationDegraded` |
| A failing integration is contained | core domain unaffected; events parked, not lost | `docs/runbooks/integration-disable.md` | — |

## Observability stack itself (E22-07)

The OTel collector, Prometheus and Grafana are **opt-in** (`--profile monitoring`)
and are **never a SPOF**: the API drops spans silently when the collector is
unreachable, and metrics are pull-based. They do not run on the quorum/witness
node.
