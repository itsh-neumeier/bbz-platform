# .ai/CURRENT_STATE.md

## Current phase
Phase 0 – Repository Foundation **complete**: merged to `main` via PR #2
(2026-08-28), issue #1. CI and Security workflows green on `main`.

Transitioning to Phase 1 – Core Domain (see "Next target" below). Prerequisite
ADRs 0007–0018 still move from Proposed to Accepted on review before Phase 1
implementation starts.

## Existing reference
A functional HTML mockup defines important UX/feature behavior. **It is not yet in
the repository** — it must be committed under `docs/mockup/` before Phase 3 and is
required as the frontend test baseline (open item below).

## Implemented in production code
Foundation skeleton only — **no domain logic, no productive vendor integrations**:

- `server/` (bbz_core): FastAPI app; `/health/live|ready|details`,
  `/cluster/status` (honestly-labelled stub), `/api/v1/meta`, versioned OpenAPI;
  structured JSON logging + correlation id; `pydantic-settings`; uniform error
  envelope; command/idempotency envelope model; integration-manifest discovery.
- `packages/integration-sdk`: manifest JSON-Schema + validation, vendor-neutral
  provider `Protocol`s (telephony/monitor/video/weather/alarm-ingress),
  capability model, diagnostics interface, normalized event name enums.
- `packages/rule-dsl`: safe structured-expression parser + allowlists;
  `evaluate()` intentionally raises `NotImplementedError` (ADR-0010).
- `packages/event-schemas`: domain-event envelope + normalized telephony-event
  JSON Schemas, loader.
- `integrations/`: **mock only** — `telephony_mock`, `monitor_mock`,
  `coda_video` (video + alarm-ingress mock). Placeholders (README only):
  `telephony_sip`, `telephony_cucm`, `monitor_weytec`, `siedle`, `dwd`.
- DB: async SQLAlchemy engine + readiness probe; Alembic wired; migration
  `0001_baseline` (extensions only, reversible).
- `apps/web`: Vue 3 + PrimeVue app shell (left sidebar / topbar / content /
  keyboard-resizable comms sidebar), design tokens, reduced-motion contract,
  i18n (DE), Vitest + Playwright config, a11y-lint config.
- Placeholders (README only): `services/cucm-cti-gateway`,
  `agents/bbz-client-agent`, `agents/bku-agent`, `apps/bbz-kiosk`, `deploy/*`.
- CI: `.github/workflows/ci.yml` (backend lint/type/import-linter/pytest +
  Alembic up/down/up; frontend lint/type/test; commitlint; compose config) and
  `security.yml` (gitleaks, pip-audit, Trivy FS). Dependabot, pre-commit,
  CODEOWNERS, PR/issue templates.
- Architecture boundaries enforced by `import-linter` (core ↛ integrations;
  api/domain ↛ SDK).

## Test status (`main`, after Phase 0 merge + dependency hygiene)
- Python: **50 passed** (pytest 9.x), `ruff` + `ruff format` clean, `mypy
  --strict` clean, `import-linter` 3/3 contracts kept.
- CI workflow **green**: backend (lint/type/import-linter/pytest+coverage,
  Alembic upgrade/downgrade/upgrade against real PostgreSQL), commitlint,
  `docker compose config`.
- Security workflow **green**: gitleaks, pip-audit (strict, third-party deps),
  Trivy FS.
- Frontend job now runs `lint` + `typecheck` + `unit` and all pass, but is still
  **continue-on-error**; dropping that (the DoD hardening) is tracked with the
  coordinated frontend upgrade in issue #14.
- Runtime is **Python 3.13** (`python:3.13-slim` image, CI + security workflows);
  ADR-0008 floor stays "3.12+". Bump to 3.14 deferred until `asyncpg`'s pin can
  move (no cp314 wheel below 0.31) — issue #13 / PR #15.
- Dev stack (`docker compose --profile core`) **verified end-to-end** on
  2026-08-28: `api` (health/ready, meta, cluster stub, OpenAPI, `/docs`),
  Alembic `0001_baseline`, Postgres, etcd, and the Vue shell on `:5173` with the
  API dev-proxy (`VITE_API_PROXY_TARGET`).

## Dependency maintenance (2026-08-28)
Dependabot backlog cleared: GitHub Actions bumped (`checkout` v7, `setup-python`
v7, `setup-node` v7), Python dev-tooling group (pytest 9, mypy 2, ruff 0.16,
…). Deferred as dedicated tasks: coordinated `apps/web` major upgrades (PrimeVue
5 / Pinia 4 / vue-router 5 / vue-i18n 11 / Vite 8 — issue #14).

## Next target
Phase 1 – Core Domain: identity, roles, permissions, workplaces, events, event
ownership, audit, event stream, EPK workflow engine. Prerequisite ADRs 0007–0018
move from Proposed to Accepted on review.

## New ADRs (this phase)
0007 monorepo layout · 0008 backend stack & boundaries · 0009 agent language (Go,
proposed) · 0010 rule DSL · 0011 event log + outbox/inbox · 0012 API/idempotency
conventions · 0013 frontend stack & a11y · 0014 CI/CD & supply chain · 0015
config & secrets · 0016 Cayuga→Coda consolidation (accepted) · 0017 time handling
(UTC) · 0018 distributed config store (etcd).

## Open external dependencies
- exact Cisco CUCM version/SU and productive cluster/CTI configuration (§8.18)
- Weytec API documentation
- Coda Video (HxGN dC3 Video) partner/API/SDK documentation for alarm ingress and
  camera/display control
- Siedle Access DTMF door-open profile (secret/config; operating concept)
- Entra ID / LDAP connection parameters

CUCM/Coda/Weytec/Siedle integrations are built strictly from documented vendor
interfaces. No customer-specific or vendor API is invented.

## Open decisions / questions (carried from planning)
- commit the functional HTML mockup into the repo
- confirm ADR-0009 (Go vs. Rust for agents)
- BKU workstation OS + corporate browser (launch mechanism)
- offline→online conflict-resolution policy
- Electron: load web build from server vs. bundle
- multi-BBZ / multi-tenancy scope (`region`/`bbz` scopes)
- LICENSE choice + container-registry mirror (see `docs/repo-settings.md`)
- synchronous vs. asynchronous PostgreSQL replication mode
- audit immutability mechanism (append-only + DB grants / hash-chain / WORM)
- co-determination / DPIA for BKU session monitoring + remote logout/restart

## Newly accepted planning requirements
- BKU Agent architecture
- centrally managed operational app/link catalog
- technical telephony endpoints/triggers
- Siedle DTMF door-opening process
- Coda Video camera + panic/duress alarm ingestion mapped to BBZ event + EPK
- BMA call-to-event automation
- graphical EPK workflow engine with AND/OR/XOR
