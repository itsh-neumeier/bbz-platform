# Optional observability stack

Roadmap **E22-07**, MASTER_PROMPT §20 ("optional telemetry collector"). The
alert rules (E22-06) live next to this in `alerts/`.

```
collector/otel-collector-config.yaml   # OTLP in -> debug (+ your trace backend)
prometheus/prometheus.yml              # scrapes the API metrics + loads alerts/
grafana/provisioning/                  # datasource + dashboard providers
dashboards/*.json                      # Cluster / Telephony / Triggers
```

## Run it (dev)

```sh
docker compose --profile core --profile monitoring up
```

- Grafana: <http://localhost:3000> (`admin` / `${GRAFANA_ADMIN_PASSWORD:-admin}`)
  — the three BBZ dashboards are auto-provisioned in the *BBZ* folder.
- Prometheus: <http://localhost:9090> — the `bbz-api` target is **DOWN** until
  you give the scrape a bearer token (see `prometheus/prometheus.yml`); the
  alert rules are loaded regardless.
- OTel collector: OTLP on `:4318` (http) / `:4317` (grpc), health on `:13133`.
  Point the API at it: `BBZ_OTEL_TRACES_EXPORTER=otlp`,
  `BBZ_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` (E22-01).

## It is never a SPOF

- **Not on the quorum/witness node** — the `monitoring` profile is only in the
  dev `docker-compose.yml`; `deploy/quorum` runs etcd only (enforced by
  `test_deploy_topology.py`).
- The API drops spans silently when the collector is unreachable; metrics are
  pull-based. A dead observability stack does not affect event or call handling.

## Not in scope (E22-07)

Running a trace store (Tempo/Jaeger), Alertmanager routing, long-term metric
storage, dashboard-as-code beyond the JSON here. Target SLOs are in
`docs/observability/slo.md`.
