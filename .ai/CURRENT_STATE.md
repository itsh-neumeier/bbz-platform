# .ai/CURRENT_STATE.md

## Current phase
Phase 0 complete. **Phase 1 – Core Domain in progress**, working the roadmap
issues in order (see `.ai/ROADMAP.md`, tracking issue #18).

### Epic 02 – Identity / RBAC: **COMPLETE (14/14)**
#20 ADR gate · #27 identity schema · #28 RBAC schema (scoped
`role_permissions` + Rule-DSL `condition`) · #29 local password auth
(`bbz_core.auth`: Argon2id / policy / lockout) · #30 `AuthProvider` registry
(local real; OIDC/LDAP stubs) · #31 sessions + `/api/v1/auth/*` (HS256 JWT,
hashed refresh, `sessions`, CSRF) · #32 permission catalog + `PermissionService`
(`bbz_core.authorization` layer) · #33 scope resolver · #34 `require("perm")`
dependency + "every write route is gated" contract test · #35 RBAC admin API
(roles/permissions/assignments/groups, last-admin guard) · #36 user admin API
(create-with-login, deactivate revokes sessions, password reset) · #37 presence
(effective-offline without a session) · #38 `audit_events` + authentication
events + `GET /api/v1/audit` · #39 TOTP (`local_totp`, recovery codes, Fernet
at rest, `totp_required` on login) · #40 seed (64 permissions, 5 built-in roles).

Migrations `0002`–`0008` on `main`. `bbz_core` packages now: `auth`, `authorization`,
`audit`. API routers under `/api/v1`: `auth`, `system`, `rbac`, `users`,
`presence`, `auth/totp`, `audit`. Test infra: `db` fixture (real PostgreSQL or
`skip`; drops schema on teardown so CI's post-pytest Alembic step is clean).
`import-linter`: 4 contracts (added `authorization` ↛ infra/api/sdk).
New deps: `pyjwt`, `argon2-cffi`, `pyotp`, `cryptography>=46.0.7`.

### Epic 03 – Event Core: **in progress (5/16)**
#41 event schema (`events`, `event_status_history`, `event_assignments` with a
partial-unique "one active assignment", `event_notes`; enum cols = `VARCHAR`+`CHECK`;
migration 0009) · #42 append-only `domain_events` log (`event_seq` BIGINT identity,
`append_event()` in-tx invariant + envelope validation, `read_since()`; migration
0010) · #43 durable command dedupe: `commands` table (`command_id` PK, request
hash, stored result), `bbz_core.infra.idempotency` (`IdempotencyStore` claim →
replay / `CommandConflictError` on body mismatch / `CommandInProgressError` while
in flight, `idempotent()` context manager, `purge_stale`/`purge_completed`);
migration 0011 · #44 pure event aggregate + state machine in
`bbz_core.domain.events` (`EventStatus`/`EventPriority` moved here as the
canonical vocabulary; infra models re-use them for `CHECK`s). `EventAggregate`
with `create/accept/acknowledge/open/archive/reactivate/assign/take_over`;
invalid transition → `InvalidTransition`, nothing mutated; `collect_events()`
drains queued `DomainEventData`. 100 % branch coverage (ADR-0008 gate) · #45
(E03-05) `bbz_core.infra.repositories.events.EventRepository`: `get`/`require`
(row + active assignment → aggregate), `add` (new event → `events` row +
`event_status_history` + `EVENT_CREATED`), `save` (guarded `UPDATE … WHERE
version = :expected` → `VersionConflictError`; drains pending events into
`domain_events` + status-history + assignment reconciliation, all in the
caller's TX — `_require_tx` mirrors `append_event`). 100 % coverage.

**Next:** #46 (E03-06) `POST /api/v1/events` — first write endpoint: wires
`require("events.create", scope)` + command envelope + `idempotent()` +
`EventAggregate.create` + `EventRepository.add`. Then #47+ accept/ack/open/…
See `.ai/ROADMAP.md` Epic 03.

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

## Delivery roadmap (2026-08-28)
`.ai/ROADMAP.md` is the full delivery plan: **24 Epics, 279 single-branch
issues**, each with the mandatory template (goal / background / scope /
out-of-scope / dependencies / acceptance criteria / tests / security / HA /
permissions / audit events). All 279 issues exist on GitHub with one milestone
per epic (`01 …` – `24 …`) and `epic:*` / `phase:*` / `area:*` labels;
cross-issue dependencies are annotated as `E##-## (#nnn)` in the bodies.
Tracking issue: #18. The roadmap also schedules six new/confirmed ADRs
(ADR-0009 accept, ADR-0019 secret store, 0020 audit immutability, 0021 PG
replication mode, 0022 Electron load strategy, 0023 SIP gateway) and one
permission-catalog addition (`agents.manage`).

## Next target
Phase 1 – Core Domain (Epics 02–05). The Phase-1 ADR gate (**E01-01** / #20) is
**cleared** — see below. Start with **Epic 02 Identity / RBAC** (#27 ff.,
schema-first: E02-01 #27 → E02-02 #28 → …). HA Cluster (Epic 06) runs in
parallel from Phase 2.

## Architecture ADRs — status (after E01-01 / #20, 2026-08-29)
**Accepted:** 0001, 0002 (baseline), 0003, 0004, 0005, 0006, 0007 monorepo
layout, 0008 backend stack & boundaries, 0010 rule DSL, 0011 event log +
outbox/inbox, 0012 API/idempotency conventions, 0013 frontend stack & a11y, 0014
CI/CD & supply chain, 0015 config & secrets, 0016 Cayuga→Coda consolidation, 0017
time handling (UTC), 0018 distributed config store (etcd).

**Still Proposed / decision pending:**
- **0009** agent language (Go) — decided in Epic 09 issue E09-01 (#145).

**Open points recorded on accepted ADRs:**
- ADR-0013: the coordinated `apps/web` major upgrade (PrimeVue 5 / Pinia 4 /
  vue-router 5 / Vite 8) is evaluated in issue #14; baseline stays PrimeVue 4.
- ADR-0015: the concrete runtime secret-store product → dedicated **ADR-0019**
  (E01-03 / #22), required before staging.

**New ADRs scheduled by the roadmap:** 0019 secret store (E01-03 / #22), 0020
audit immutability (E04-10 / #66), 0021 PostgreSQL replication mode (E06-02 /
#82), 0022 Electron load strategy (E08-07 / #143), 0023 SIP gateway (E13-02 /
#271).

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
