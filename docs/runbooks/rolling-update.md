# Runbook: rolling update

Update the two BBZ application nodes one at a time with no client outage
(MASTER_PROMPT §21, ADR-0001). etcd and PostgreSQL are **not** touched here —
this is an `bbz-api` / `bbz-web` image roll only.

Tool: `tools/rolling-update.sh` (run from a control host).

```sh
NODES="bbz-srv02 bbz-srv01" \
IMAGE="ghcr.io/itsh-neumeier/bbz-api@sha256:<digest>" \
API="https://bbz.example.internal" \
TOKEN="<bearer with system.cluster.manage>" \
MIGRATION_CHECKED=1 \
  ./tools/rolling-update.sh
```

## Order

1. **Pre-flight** (`preflight()` — the script aborts here, nothing changed):
   - `/cluster/status` reports `stub:false`, `dcs_healthy:true`, `quorum:true`.
   - no node's `replication_lag_bytes` exceeds `LAG_LIMIT` (1 MiB).
   - `MIGRATION_CHECKED=1` — you have confirmed CI's **`migration-compat`** job
     is green for this digest, i.e. the schema at `head` is safe for the
     *currently running* app version (expand/contract — `docs/CONVENTIONS.md`).
2. Audit `ROLLING_UPDATE_STARTED` (`POST /api/v1/system/rolling-update`).
3. For each node, **passive/standby first** (`NODES` order):
   1. `docker compose pull api && docker compose up -d --no-deps api` on that
      node (its `.env` `BBZ_API_IMAGE` is rewritten; a `.env.bak` is kept).
   2. While the new container boots it answers `/health/ready` with `503`
      (E06-05), so the node's own Caddy — and any front load balancer — stop
      routing to it; the client agent uses the other node. This is the drain.
   3. **Health gate**: poll `/health/ready` until green (`GATE_RETRIES *
      GATE_SLEEP`, default 120 s). If it never goes green → **abort**, the
      later node is untouched.
   4. Re-run pre-flight. If the cluster degraded → **abort**.
4. Audit `ROLLING_UPDATE_COMPLETED`.

## Abort / rollback

Any failed health gate or pre-flight stops the run immediately and leaves every
not-yet-updated node on the old digest. To roll back the node that was being
updated:

```sh
ssh <node> "cd /opt/bbz/deploy/node && mv .env.bak .env && docker compose up -d --no-deps api"
```

then verify `/health/ready` and `/cluster/status`. See `rollback.md`.

## Notes

- `IMAGE` **must** be pinned by digest (`@sha256:…`); the script refuses a tag
  (supply-chain — E01-04).
- The DB migration itself is applied separately and earlier, as its own
  expand step, by whoever owns the release — never mid-roll.
- Two nodes down at once (this roll + an unrelated failure) drops etcd below
  quorum; do not start a roll while the witness or a node is already down.
