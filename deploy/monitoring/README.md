# deploy/monitoring

Prometheus alerting rules for the BBZ platform (roadmap **E22-06**). The
optional collector + Grafana dashboards are **E22-07**.

```
alerts/
  bbz.rules.yml       # the alerting rules
  bbz.rules.test.yml  # promtool test cases
```

## Load into Prometheus

```yaml
# prometheus.yml
rule_files:
  - /etc/prometheus/rules/bbz.rules.yml

scrape_configs:
  - job_name: bbz
    metrics_path: /api/v1/system/metrics   # NOT public — see below
    static_configs:
      - targets: ["bbz-srv01:8000", "bbz-srv02:8000"]
```

The metrics endpoint is gated on `system.cluster.view` (E06-13). Give the
scraper a bearer token for a machine identity holding that permission, or scrape
through the reverse proxy with an internal allow-list. Alertmanager routing /
receivers are the operator's job (out of scope for E22-06).

## Validate

```sh
promtool check rules deploy/monitoring/alerts/bbz.rules.yml
promtool test  rules deploy/monitoring/alerts/bbz.rules.test.yml
```

Both run in CI (the `docker compose config` job).

## Rules — thresholds and rationale

| alert | expr (summary) | threshold | for | severity | runbook |
|---|---|---|---|---|---|
| `BbzQuorumLost` | `min(bbz_cluster_quorum) == 0` | no raft leader | 2m | critical | quorum-node |
| `BbzClusterDegradedDcs` | `min(bbz_cluster_dcs_healthy) == 0` | a node lost etcd | 3m | warning | quorum-node |
| `BbzSplitBrain` | `sum(bbz_cluster_node_is_primary) != 1` | ≠1 primary | 1m | critical | db-failover |
| `BbzReplicationLagHigh` | `max(bbz_replication_lag_bytes) > 1048576` | 1 MiB (ADR-0021 `maximum_lag_on_failover`) | 5m | warning | db-failover |
| `BbzWorkerLeaderMissing` | `sum by (singleton) (bbz_worker_leader) < 1` | no lease holder | 5m | warning | observability-alerts |
| `BbzIntegrationDown` | `bbz_integration_health == 0` | unavailable/unknown | 5m | warning | integration-disable |
| `BbzIntegrationDegraded` | `bbz_integration_health == 0.5` | degraded | 15m | info | integration-disable |
| `BbzOutboxBacklog` | `max(bbz_outbox_pending) > 100` | 100 rows | 10m | warning | observability-alerts |
| `BbzOfflineCommandsPending` | `max(bbz_commands_pending) > 50` | 50 rows | 15m | info | observability-alerts |
| `BbzApiLatencyHigh` | p95 `bbz_http_request_duration_seconds` `> 1` | 1 s | 10m | warning | observability-alerts |
| `BbzApiErrorRateHigh` | 5xx ratio `> 0.05` | 5 % | 10m | warning | observability-alerts |

Thresholds are conservative starting points — tune per site once there is a
baseline. The cluster / DB numbers are anchored to ADR-0021.
