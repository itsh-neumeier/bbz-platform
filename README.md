# BBZ / 3-S-Zentrale Platform

Highly available, modular control-room platform for a Bahnhofsbetriebszentrale
(BBZ) / 3-S-Zentrale: event management, telephony & call documentation, guided
operating procedures (EPK), event ownership/handover, contacts & priorities, DWD
weather, monitor routing, audit/archive, and an integration framework.

## Source of truth

`AGENTS.md` and `.ai/**` are the vendor-neutral source of truth. Read
`AGENTS.md`, then `.ai/WORKSPACE.md`, `.ai/ARCHITECTURE.md`, `.ai/RULES.md`,
`.ai/CURRENT_STATE.md`, and the ADRs under `.ai/DECISIONS/` before any task.

- Architecture map: `docs/ARCHITECTURE_OVERVIEW.md`
- Conventions: `docs/CONVENTIONS.md`
- Dev setup: `docs/DEV_SETUP.md`
- ADR process + index: `docs/adr/README.md`

## Status

**Phase 0 – Repository Foundation** (see `.ai/CURRENT_STATE.md`). Skeleton only:
FastAPI core with health/cluster/meta endpoints, the integration SDK, mock
providers, an app shell, CI and the ADR system. **No domain logic and no
productive CUCM / Coda Video / Siedle / Weytec integrations.**

## Layout

```
server/         Python backend (bbz_core): api · domain · infra · integrations_host · workflow_engine
packages/       integration-sdk · rule-dsl · event-schemas
integrations/   dwd · telephony_{mock,sip,cucm} · monitor_{mock,weytec} · coda_video · siedle
services/       cucm-cti-gateway (Java, JTAPI — placeholder)
apps/           web (Vue 3 + PrimeVue) · bbz-kiosk (Electron — placeholder)
agents/         bbz-client-agent · bku-agent (placeholders)
deploy/         HA topology assets (Patroni · etcd · reverse-proxy · quorum)
docs/           setup, conventions, runbooks, domain catalogs
.ai/            vendor-neutral source of truth + ADRs
```

## Quick start

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt
ruff check . && mypy server/bbz_core packages/*/bbz_* && lint-imports && pytest
cp .env.example .env && docker compose --profile core up --build
```
