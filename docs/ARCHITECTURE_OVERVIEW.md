# Architecture overview (map)

This is a navigation aid. The authoritative content is `.ai/**` and the ADRs.

```
                 Electron Kiosk (apps/bbz-kiosk)         BKU workstation
                 embeds apps/web  ─┐                     ┌─ agents/bku-agent
                                   │                     │  (typed allowlist)
   agents/bbz-client-agent ────────┤                     │
   (discovery, failover, cache,    │                     │
    offline outbox)                ▼                     ▼
                        ┌───────────────────────────────────────┐
                        │  Edge (deploy/reverse-proxy)           │
                        └───────────────┬───────────────────────┘
              ┌─────────────────────────┴─────────────────────────┐
     BBZ-SRV01 (active)                                   BBZ-SRV02 (active)
     server/ (bbz_core)                                   server/ (bbz_core)
       api → domain → infra                                 ...
       integrations_host ──► integrations/* (dwd, telephony_*, monitor_*, coda_video, siedle)
       workflow_engine (EPK)                                services/cucm-cti-gateway (Java, JTAPI)
              │                                                     │
              └───────────── PostgreSQL (Patroni) ◄────────────────┘
                     primary/standby, WAL replication
                             │
                   etcd × 3  (SRV01, SRV02, BBZ-QUORUM01 witness)
```

## Where things live

| Concern | Location | Reference |
|---|---|---|
| HTTP, health, cluster status | `server/bbz_core/api` | MASTER_PROMPT §23 |
| Pure domain (Phase 1+) | `server/bbz_core/domain` | ADR-0008 |
| DB, event store, outbox/inbox | `server/bbz_core/infra` | ADR-0011 |
| Integration plugin contracts | `packages/integration-sdk` | MASTER_PROMPT §7 |
| Safe rule DSL | `packages/rule-dsl` | ADR-0010 |
| Event JSON Schemas | `packages/event-schemas` | MASTER_PROMPT §3/§8.4 |
| Concrete integrations | `integrations/*` | ADR-0002/0004/0006 |
| Cisco JTAPI encapsulation | `services/cucm-cti-gateway` | ADR-0002 |
| Web UI | `apps/web` | ADR-0013 |
| Local agents | `agents/*` | ADR-0003/0009 |
| HA topology assets | `deploy/*` | ADR-0001/0018 |
| Cluster singletons | `server/bbz_core/workers` | ADR-0011/0018 |

## Cluster singletons (background work that must not run twice)

Some work must run on exactly one node at a time. Each such job is a **named
singleton** registered in `bbz_core/workers/registry.py`:

| name | tick | source |
|---|---|---|
| `outbox-dispatcher` | `OutboxDispatcher().run_once()` — deliver `external_action_outbox` rows | ADR-0011 |
| `workflow-timer` | `WorkflowEngineService.fire_due_timers()` — resume due EPK timers | E05-10 |
| `cucm-control-leader` *(future)* | JTAPI control ownership | ADR-0002 / E12-07 |

Every node starts every singleton (`ClusterWorkers`, wired into the FastAPI
lifespan when `BBZ_RUN_BACKGROUND_WORKERS=true`). `run_as_singleton` campaigns
for a short-lived etcd lease under `/bbz/leader/<name>` (ADR-0018) and calls the
tick only while it holds the lease; it **steps down the instant a renewal
fails**, so a dead leader is replaced within `2 × ttl`. `dedupe_key` /
`SKIP LOCKED` in the outbox make a brief overlap during hand-off harmless.

`GET /cluster/status` reports `singletons` (the names) and `leaders`
(`name → node_id` currently holding each lease).
