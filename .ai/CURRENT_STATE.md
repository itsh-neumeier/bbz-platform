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

### Epic 03 – Event Core: **COMPLETE (16/16)**
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
caller's TX — `_require_tx` mirrors `append_event`). 100 % coverage · #46
(E03-06) `POST /api/v1/events` — first write endpoint. `bbz_core.api.v1.events`
router: `require("events.create")` + `command_envelope` header dep +
`idempotent()` (replay / 409 on `CommandConflict`/`InProgress`) +
`EventAggregate.create` + `EventRepository.add`; 201 + `EventOut` + `Location`.
`_translate()` maps `VersionConflictError`→409 (+ details), `EventNotFound`→404,
`EventDomainError`→422 for the coming verbs. Scope-aware `require` and per-route
CSRF deferred to E23 (matches the other admin routers). Audit-log entry
deferred to E04 (`domain_events` row is the record). Tests: 201 / 403 / 422 /
missing X-Command-Id / duplicate replay (one event) / body-mismatch 409.

#47 (E03-07) `POST /events/{id}/accept|acknowledge|open` — three verbs sharing
`_apply_transition` (require gate + `X-Expected-Version` required + `idempotent()`
+ load/mutate/`EventRepository.save` in one TX). Wrong order → 409
(`InvalidTransition`), stale version → 409 + `details.expected_version`, dup
command → replay. Tests cover happy path / order / conflict / idempotency /
missing header / 403.

#48 (E03-08) `PATCH /events/{id}` — whitelist edit (title / description /
priority; `extra="forbid"` → 422 on unknown field), `X-Expected-Version`
required, `EventAggregate.update()` emits `EVENT_UPDATED` with a per-field
`{from,to}` diff (no-op edit → 422). Added `events.description` column
(nullable Text, migration 0012) + `description` on the aggregate, `EventOut`,
`CreateEventIn`.

#49 (E03-09) `POST /events/{id}/assign` — `require("events.assign")` +
`X-Expected-Version` + `target_user_id` (must be an existing active user, else
422). `EventAggregate.assign()` now allows **reassignment** (from/to in the
`EVENT_ASSIGNED` payload); `EventRepository` keeps the one-active-row invariant.
`_apply_transition` gained `body_fields` so the idempotency hash covers the body.

#50 (E03-10) `POST /events/{id}/takeover` — `require("events.takeover")` +
`X-Expected-Version`; only when the current owner's **server-side effective
presence** is `pause`/`offline` (else 409 + `details.owner_presence`), grabs
the event for the caller, `EVENT_TAKEN_OVER` + **mandatory** `AuditEvent`
(`EVENT_TAKEN_OVER`, before/after assignee, optional reason) written in the
same TX (`AuditWriter.record(commit=False)` added). Scope `bbz` deferred to E23.

#51 (E03-11) `POST /events/{id}/archive` (reason optional) + `.../reactivate`
(`confirm=true` **and** non-empty reason required, else 422). Both audited in
the command TX via `_apply_transition(audit_action=…)` — `AuditAction`
`EVENT_ARCHIVED` / `EVENT_REACTIVATED`. `archive()` no longer forces a reason.
Contract test: no DELETE route under `/api/v1/events` (no hard-delete).

#52 (E03-12) read endpoints in `bbz_core.infra.repositories.event_queries`
(`EventQueryRepository`) + `GET` routes, all gated `require("events.view")`:
`GET /events?queue=active` (non-archived, priority rank then age),
`GET /events` (newest-first, keyset pagination on `(created_at,id)` → stable
under concurrent inserts, `include_archived`/`status` filters), `GET /events/{id}`
(detail: description + status history + active assignee + notes). Scope filter is
a no-op hook (`_scope_filter`) until user placement (E23).

#53 (E03-13) SSE stream `GET /api/v1/events/stream?after_seq=N` — catch-up from
`domain_events` via `read_since`, then live. `bbz_core.infra.event_stream`:
`sse_stream()` async generator (`: connected` / event frames `id:`/`event:`/`data:`
/ `: heartbeat`), `EventBroker` (asyncio.Condition — latency hint only, DB poll
every 15 s is the source of truth), `notify_event_appended()` called by the 4
event write paths after commit. `event_log._envelope` → public `envelope()`.
Scope-per-connection deferred to E23. Generator unit-tested; API tests cover
auth + `/stream` vs `/{id}` routing.

#54 (E03-14) WebSocket variant `/ws/events?after_seq=N` (`bbz_core.api.ws`,
mounted app-level). Shares `event_feed` with SSE — refactored `event_stream`
to a shared `event_feed()` yielding `EventFrame | None`; `sse_stream` now wraps
it. WS: JSON messages `{type: connected|event|heartbeat}`, client `{type: ack,
after_seq}` accepted as a hint only, token via bearer/`?access_token=`/cookie,
origin check against `cors_allow_origins`, close 1008 on auth fail, send/recv
task race. Tested via `_authorize`/`_origin_allowed` unit tests + shared
`event_feed` tests.

#55 (E03-15) `GET /api/v1/events/priority-alert` → `{active, events:[{id,
priority, title}]}` — high/critical events still in `new` (unaccepted) ·
#56 (E03-16) `POST /events/{id}/notes` (`require("events.postprocess")`, kind
`work` only — postprocess deferred to Epic 20; `EVENT_NOTE_ADDED` domain event,
`idempotent()`, 404 if event missing) + `GET /events/{id}/export`
(`require("events.export")` → event detail + status history + notes + all
`domain_events` ordered by `event_seq`; writes an `EVENT_EXPORTED` audit row).
`AuditAction` gained `EVENT_EXPORTED`. `event_queries` gained `export()`.

Migrations `0002`–`0012`. Event API surface under `/api/v1/events`: create ·
accept/acknowledge/open · PATCH · assign · takeover · archive/reactivate ·
notes · GET list/`?queue=active`/`{id}`/`{id}/export`/`priority-alert`/`stream`.
WS at `/ws/events`.

### Epic 04 – Audit / Domain Events: **in progress (7/11)**
#57 (E04-01) `audit_events` schema review — added `event_seq_ref` BIGINT
(nullable, no FK; migration 0013) linking an audit row to its domain event;
ORM `before_update` / `before_delete` listeners raise `AuditImmutableError`
(append-only at the mapping level; the DB grant/trigger is E04-10/E23-09).

#58 (E04-02) `bbz_core.audit.AuditService.write()` — appends in the caller's
transaction (`AuditNotInTransactionError` otherwise), enforces a mandatory
`reason` for `REASON_REQUIRED` actions (`AuditReasonRequiredError`; currently
just `EVENT_REACTIVATED`), sets `correlation_id` + `node_id` + optional
`event_seq_ref`. `changed_fields(before, after)` → `{field:{from,to}}` diff.
Older `AuditWriter` kept for auth events / the basic read.

#59 (E04-03) event-side critical actions now use `AuditService.write` (in the
command TX): assign (`EVENT_ASSIGNED`, +diff), takeover, archive, reactivate,
export. `_apply_transition` audits `{status, assignee_id}` before/after.
`CRITICAL_ACTIONS` frozenset + a contract test that scans `bbz_core` and fails
CI if a critical action has no `AuditService` call site. RBAC/user critical
actions (E02-09/10) still carry `TODO(E04-03)` — to be wired next.

#60 (E04-04) `GET /api/v1/audit` rewritten on `AuditQueryRepository`
(`bbz_core.infra.repositories.audit_queries`): filters actor / target_type /
**target_id** / action / time range / **correlation_id**, keyset pagination on
`(occurred_at_utc, id)` → `{items, next_cursor}`, `system.audit.view` required,
`before`/`after`/`event_seq_ref` now in the output. `test_login_audit` updated
for the new `{items}` shape. (`AuditWriter.query` now unused; left in place.)

#61 (E04-05) per-`event_type` payload schemas finalized:
`event.payloads.v1.json` (one sub-schema per type), loader
`event_payload_schema()` / `known_event_types()` / `UnknownEventTypeError` in
`bbz_event_schemas`. `append_event` now validates the payload against its type
schema and **rejects an unknown `event_type`** (`UnknownEventTypeError`, an
`EnvelopeInvalidError`). `schema_version` versioning policy + per-type required
fields documented in `docs/domain/event-catalog.md` (additive→same major,
breaking→new `.vN+1.json` + migration note; no secrets in payloads).

#62 (E04-06) transactional outbox — `external_action_outbox` (migration 0014,
`dedupe_key` UNIQUE, status pending/dispatched/failed, attempts, next_attempt_at,
backoff). `bbz_core.infra.outbox.enqueue()` runs in the caller's TX;
`OutboxRepository.claim_due()` uses `FOR UPDATE SKIP LOCKED`. `bbz_core.workers.
outbox_dispatcher.OutboxDispatcher` — handler registry (`noop`/`notify`),
`run_once()` processes each row in its own TX, exponential backoff to
`MAX_ATTEMPTS=8` then `failed`; status update + `EXTERNAL_ACTION_DISPATCHED` /
`EXTERNAL_ACTION_FAILED` audit commit together. `run_forever()` for E04-08.

#63 (E04-07) provider-event inbox — `provider_event_inbox` (migration 0015,
`dedupe_key` UNIQUE, `provider`, `provider_event_id`, `raw_ref`/`raw_hash`,
`normalized` jsonb, `received_at`/`processed_at`). `bbz_core.infra.inbox.ingest()`
→ `IngestResult(outcome=new|duplicate, inbox_id, dedupe_key)`;
`derive_dedupe_key()` = `provider:<id>` or `provider:sha256:<payload hash>` when
the provider has no stable id (key-order-insensitive). `mark_processed()`
idempotent.

**Next:** RBAC/user critical-action audit wiring (deferred from #59) and #64
(E04-08) singleton worker via etcd lease. See `.ai/ROADMAP.md` Epic 04.

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
