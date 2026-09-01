# Health endpoints

`bbz_core.api.health`. Three surfaces, three audiences.

| endpoint | auth | audience | on failure |
|---|---|---|---|
| `GET /health/live` | none | "is the process up" (Docker `HEALTHCHECK`) | — |
| `GET /health/ready` | none | the load balancer (Caddy `health_uri`) | `503 not_ready` → node drained |
| `GET /health/details` | `system.cluster.view` | operators / diagnostics | `200` with per-check `ok:false` |

## `/health/ready`

Checked in order, ~2 s timeout each — any failure ⇒ `503`:

1. **database** — this node can reach its PostgreSQL.
2. **cluster** — the local Patroni `/readiness` is `200` (not mid rejoin / replay,
   E06-05); skipped when no local Patroni is configured.

## `/health/details` (E22-04)

A per-dependency status matrix + build provenance. Gated on `system.cluster.view`
— it is a diagnostic surface, not an LB probe. No secret or internal endpoint is
in the body.

```json
{
  "service": "bbz-api", "version": "0.0.0",
  "environment": "production", "node_id": "BBZ-SRV01",
  "build": { "version": "0.0.0", "revision": "<git sha>", "built_at": "<iso>" },
  "checks": [
    { "name": "database", "ok": true,  "detail": null, "duration_ms": 1.2 },
    { "name": "cluster",  "ok": true,  "detail": "patroni ready", "duration_ms": 8.4 },
    { "name": "dcs",      "ok": true,  "detail": null, "duration_ms": 12.1 }
  ]
}
```

- **database** — `SELECT 1`.
- **cluster** — the local Patroni `/readiness` (as `/health/ready`).
- **dcs** — can this node reach at least one configured etcd endpoint. The full
  DCS / quorum / topology picture is `/cluster/status` (E06-04), **not** this
  endpoint.
- **build** — `revision` / `built_at` come from `BBZ_BUILD_REVISION` /
  `BBZ_BUILD_TIME`, injected as Docker build args (`server/Dockerfile`). A source
  checkout reports `"unknown"`.

`duration_ms` is the wall time of that probe — a slow-but-ok dependency shows up
before it starts failing.
