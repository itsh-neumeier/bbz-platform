# Runbook: observability alerts

Covers the BBZ alert rules (`deploy/monitoring/alerts/bbz.rules.yml`, E22-06)
that do not have a dedicated runbook. Cluster / DB alerts point at
`db-failover.md` and `quorum-node.md`; integration alerts at
`integration-disable.md`.

Metrics reference: `docs/metrics.md`. Every value below is per node — check
`GET /api/v1/system/metrics` on each.

---

## BbzWorkerLeaderMissing

**Means:** no node holds the etcd lease for a cluster singleton
(`{{ $labels.singleton }}`) — its background work is not running.

- `outbox-dispatcher` down ⇒ external actions (notifications, camera cues, door
  DTMF) queue in `external_action_outbox` and are not sent.
- `workflow-timer` down ⇒ EPK timer steps never fire.
- `trigger-engine` down ⇒ inbound provider events are ingested but not evaluated.
- `weather-refresh` / `directory-sync` / `integration-health` down ⇒ stale data.

**Check:** `bbz_worker_leader{singleton="..."}` on every node — all 0.
`GET /cluster/status` → `leaders` map and `dcs_healthy` / `quorum`.

**Fix:**
1. If `BbzQuorumLost` / `BbzClusterDegradedDcs` is also firing — fix that first
   (`quorum-node.md`); leader election needs etcd.
2. Confirm `BBZ_RUN_BACKGROUND_WORKERS=1` on the app nodes.
3. Restart one app node — it re-campaigns for every unheld singleton on boot.
4. `bbz_outbox_pending` should start falling within one dispatcher cycle.

---

## BbzOutboxBacklog

**Means:** `bbz_outbox_pending > 100` for >10m — the outbox is not draining.

**Check:**
- `BbzWorkerLeaderMissing{singleton="outbox-dispatcher"}` firing? → that runbook.
- Otherwise a downstream is failing every attempt. Query the DB:
  `SELECT action_type, status, count(*), max(attempts) FROM external_action_outbox
   GROUP BY 1, 2;` — rows stuck at `failed` with `attempts = 8` have exhausted
  retries; `pending` with a future `next_attempt_at` are backing off.

**Fix:** repair the downstream (the notify target, the integration). Rows move to
`dispatched` on the next successful attempt; `failed` rows need a manual replay
once the cause is fixed.

---

## BbzOfflineCommandsPending

**Means:** `bbz_commands_pending > 50` for >15m — many commands accepted but with
no stored result.

**Check:** `SELECT endpoint, count(*) FROM commands WHERE result_status IS NULL
GROUP BY 1 ORDER BY 2 DESC;` — a single endpoint dominating points at a stuck
handler; spread across many points at clients that submitted offline and have not
reconnected to collect results.

**Fix:** usually self-heals as clients reconnect. A stuck handler needs
investigation; `tools`-side `purge_stale` clears rows past the replay window.

---

## BbzApiLatencyHigh / BbzApiErrorRateHigh

**Means:** p95 request latency >1s, or >5% 5xx, for >10m.

**Check:**
- `bbz_db_pool_connections{state="in_use"}` near the pool ceiling, or
  `state="overflow"` > 0 ⇒ DB saturation / a leak.
- `bbz_replication_lag_bytes` high ⇒ reads on a lagging standby.
- Correlate with a deploy (`ROLLING_UPDATE_*` audit markers) — roll back if so
  (`rolling-update.md`).
- The structured logs carry `trace_id`; pull the slow traces
  (`docs/observability/tracing.md`) to see which span dominates.

**Fix:** depends on the cause — scale the pool (`BBZ_DATABASE_POOL_SIZE`), fix
the slow query, or roll back.
