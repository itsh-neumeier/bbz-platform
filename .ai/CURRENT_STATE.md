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

### Epic 04 – Audit / Domain Events: **COMPLETE (11/11)**
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

#64 (E04-08) application leader election (ADR-0018) —
`bbz_core.infra.leader`: `LeaderElection` ABC, `LocalLeaderElection` (always
leader, single-node dev/tests), `EtcdLeaderElection` over etcd's v3 HTTP/JSON
gateway (no gRPC dep — lease grant + `kv/txn` CAS on `/bbz/leader/<name>` +
`lease/keepalive`, immediate step-down on any error). `leader_election_for(name)`
picks the backend from `BBZ_WORKER_LEADER_BACKEND` (`""`→local, `"etcd"`).
`bbz_core.workers.singleton.run_as_singleton(election, do_work, ttl, stop)` —
campaign / work-while-leader / renew / step-down, audits `WORKER_LEADER_CHANGED`.
New settings: `worker_leader_backend/_ttl_seconds/_prefix`.

#65 (E04-09) correlation-id propagation verified end-to-end: the
`CorrelationIdMiddleware` contextvar already flows into `append_event` /
`AuditService.write` / outbox `enqueue` / inbox `ingest` and the
`x-correlation-id` response header. Takeover now also `enqueue`s a `notify`
outbox row (in the command TX) so one command touches all four sinks; the
integration test asserts one shared `correlation_id` across
`domain_events` + `audit_events` + `external_action_outbox` for both a
supplied and a server-generated id.

#66 (E04-10) audit immutability at the DB level — **ADR-0020** (Proposed):
`audit_events` / `domain_events` get a `BEFORE UPDATE OR DELETE` trigger
(`bbz_forbid_row_mutation`) that always `RAISE EXCEPTION`. Created both by a
SQLAlchemy `after_create` DDL hook (`make_append_only` in `models/base.py`, so
`create_all` in tests/dev matches) and by migration 0016 for provisioned DBs.
`DROP TABLE` (DDL) is unaffected. Hash-chain deferred (ADR-0020 rationale).
Tests: raw SQL UPDATE/DELETE on both tables → `DBAPIError`, INSERT still works.

#67 (E04-11) replay / catch-up consistency suite
(`server/tests/test_replay_consistency.py`): event catch-up by `event_seq`
after a simulated drop loses/duplicates nothing (incl. events created while
"offline"); inbox double-delivery → one processing; outbox worker killed
mid-dispatch → row ends `dispatched` exactly once with one committed side
effect; two concurrent dispatchers deliver a row once (`SKIP LOCKED`).

Migrations `0002`–`0016`. `bbz_core` now also has: `workers/` (outbox
dispatcher, singleton runner), `infra/outbox.py`, `infra/inbox.py`,
`infra/leader.py`, `infra/event_stream.py`; `audit/` gained `AuditService` +
`CRITICAL_ACTIONS`. `/ws/events` mounted app-level.

**Open follow-up:** RBAC/user critical-action audit wiring is still deferred
(code carries `TODO(E04-03)`); the code comments point at #66/E04-10 — do it
alongside E23 hardening.

### Epic 05 – EPK Workflow Engine: **COMPLETE (13/13)**
#68 (E05-01) `bbz_rule_dsl.evaluate()` implemented — total, side-effect-free,
deterministic predicate over a typed `Context`. Operators
`eq/ne/in/not_in/lt/lte/gt/gte/and/or/not/exists`; type mismatch / bad arity /
unknown field-op / nesting > 64 → `RuleDslError`, never "silently true". Depth
guard for totality. Tests: per-operator + edge cases + a Hypothesis fuzz suite
(random AST → never a raw crash, always deterministic); 100 % branch coverage.
Added `hypothesis` to `requirements-dev.txt`.

#69 (E05-02) typed context registry — `bbz_rule_dsl.context`: `FieldType`
(string/number/boolean/datetime/list), `ContextSchema(name, fields)` with
`validate(expr)` (publish-time: unknown field → `UnknownField`; `lt` on a
non-orderable field, number-field vs string-literal, `in` against a non-list,
wrong list-item type → `RuleDslError`). `TRIGGER_CONTEXT` (15 fields) and
`WORKFLOW_CONTEXT` (8 fields) are **separate** — a workflow condition can't read
a trigger field. `model.parse()` no longer allowlists field names (that moved
to `ContextSchema`); `model.Context` accepts any resolved values.

#70 (E05-03) schema `workflow_templates` (key, name, owner) +
`workflow_template_versions` (template_id, version_no, lifecycle
draft/validated/published/deprecated, `definition` jsonb, changelog,
published_at/by) — migration 0017, `(template_id, version_no)` unique. A
`BEFORE UPDATE` trigger freezes a **published** version's `definition`
(lifecycle transitions still allowed). `bbz_core.infra.models.workflow`.

#71 (E05-04) EPK graph model — `workflow.graph.v1.json` (event/function/
connector nodes; function `kind` ∈ manual/confirmation/documentation/
integration_action/notification/timer/event_update; connector `and|or|xor` +
`split|join`; edges with optional rule-DSL `condition`). `bbz_core.domain.
workflow.graph`: `validate_graph()` (schema + unique keys + edge endpoints +
`start` exists) and `derive_index()` (deterministic, key-ordered).
`workflow_graph_nodes`/`_edges` derived tables (migration 0018);
`infra.repositories.workflow_graph.rebuild_graph_index()` replaces a version's
index rows in the caller's TX (idempotent).

#72 (E05-05) runtime schema (migration 0019, `bbz_core.infra.models.
workflow_runtime`): `workflow_instances` (event_id, template_version_id
RESTRICT, status), `workflow_tokens` (node_key, state active/waiting/consumed),
`workflow_task_results` (result jsonb, completed_by/at), `workflow_decisions`
(connector_node_key, chosen_branches, auto). A `BEFORE INSERT` trigger on
`workflow_instances` rejects a `template_version_id` whose version isn't
`published`. One event may have many instances (no unique on event_id).

#73 (E05-06) publish validation — `bbz_core.domain.workflow.publish.
validate_publishable(definition, known_capabilities=…)` → `[ValidationIssue]`
(empty = publishable). Rules: start is an event with no predecessor; every node
reachable + a reachable end; split 1-in/≥2-out, join ≥2-in/1-out, non-connectors
never branch; XOR split ≤1 unconditioned branch; OR split branches all labelled;
`integration_action`/`notification`/`timer` required props; integration
capability exists; a cycle needs a connector with `props.reentry`. 100 % branch
coverage. `AuditAction.WORKFLOW_TEMPLATE_VALIDATED` added (wired with the
lifecycle API, E05-07/08).

#74 (E05-07) template-version lifecycle service + API —
`bbz_core.infra.repositories.workflow_lifecycle.WorkflowLifecycleService`:
`create_draft_version` / `edit_draft` (draft only, else 409) / `validate`
(runs `validate_publishable`; issues → returned, stays draft; clean →
lifecycle `validated` + `rebuild_graph_index` + `WORKFLOW_TEMPLATE_VALIDATED`)
/ `publish` (needs `validated` + a changelog, else 409/422; stamps
`published_at/by`, `WORKFLOW_TEMPLATE_PUBLISHED`) / `deprecate` (published
only, `WORKFLOW_TEMPLATE_DEPRECATED`). Each method commits its own TX and
audits in it. `bbz_core.api.v1.workflows` router (`workflow-templates`,
`workflow-template-versions/{id}/validate|publish|deprecate`, PATCH edit),
all gated `workflows.view` / `workflows.manage_templates`; `_translate()`
maps the trigger's "published definition is immutable" `DBAPIError` → 409.
All 3 workflow actions added to `CRITICAL_ACTIONS`.

#75 (E05-08) token engine — AND split/join + token semantics.
`bbz_core.domain.workflow.engine` (pure, deterministic): `advance(graph,
tokens)` drives every active token to quiescence — an **event** node is a
pass-through, a **function** node parks its token (`waiting`), an **AND
split** emits one token per outgoing edge, an **AND join** fires only once a
token is parked for every incoming edge (matched by `inbound_edge_key`).
`resume_function(graph, tokens, node_key)` moves a completed step's token on.
XOR/OR raise (E05-09). A totality budget bounds a cycle without a re-entry
rule instead of hanging. `bbz_core.infra.repositories.workflow_engine.
WorkflowEngineService`: `start_instance` (seeds the start token, the
migration 0019 trigger enforces "published"), `complete_step` (records a
`WorkflowTaskResult`, audits `ACTION_STEP_COMPLETED`, advances — idempotent:
a second call for the same node is a no-op), `advance_instance` (re-drives
from the persisted token state, so a failover resumes consistently). Each
method commits its own transaction. Migration 0020 adds
`workflow_tokens.inbound_edge_key`. `ACTION_STEP_COMPLETED` joins
`CRITICAL_ACTIONS`.

#76 (E05-09) XOR / OR split & join. The engine
(`bbz_core.domain.workflow.engine`) now also takes a condition `context` and
the operator `decisions` recorded so far. **XOR split** — an operator
decision if one exists, else the first branch (edge-key order) whose rule-DSL
`condition` holds, else the unconditioned default; if nothing resolves the
token parks and waits — never a wrong path. **XOR join** fires on the first
arrival. **OR split** — a decision, else every branch whose guard holds or
has none. **OR join** fires once a token has arrived and no other live token
can still reach it (so it waits for exactly the activated branch set). Auto
selections are reported so the service writes a `workflow_decisions` row
(`auto=true`) + a `WORKFLOW_DECISION_MADE` audit entry; `WorkflowEngineService.
decide(instance, connector, [edge_keys], actor_id=…)` records an operator
choice (`auto=false`), wakes the parked token and resumes — idempotent per
connector. The condition context is built from the pinned event
(`event_priority`/`status`/`source`/`bbz_id`/`workplace_id`) plus
`step_completed_count`. `WORKFLOW_DECISION_MADE` joins `CRITICAL_ACTIONS`. The
`workflows.execute` gate for `decide` lands with the operator API (E05-10 ff.).

#77 (E05-10) task-kind runtime. `bbz_core.domain.workflow.tasks` classifies
function `kind`s; `WorkflowEngineService._settle()` runs after every advance:
`manual`/`confirmation`/`documentation` keep the token parked until an
operator `complete_step`; `timer` stamps `workflow_tokens.resume_at`
(migration 0021) and `WorkflowEngineService.fire_due_timers()` (a worker)
resumes it once due — persisted, so it survives a restart;
`integration_action`/`notification`/`event_update` enqueue exactly one
`external_action_outbox` row (`dedupe_key = workflow-step:<instance>:<node>:
attempt-0`, action_type `integration`/`notify`/`event_update`) and the token
moves on, the side effect running exactly-once via the dispatcher. Each auto
/ timer step writes an `ACTION_STEP_COMPLETED` audit row. No arbitrary
scripts — only typed outbox actions (§29/§33).

#78 (E05-11) instance pinning & start from an event.
`POST /api/v1/events/{id}/workflow` (`{template_key}`, `require
("workflows.execute")`) → `WorkflowEngineService.start_for_event` resolves the
template's **current** PUBLISHED version (highest `version_no`), pins a new
`WorkflowInstance` to it and runs. Idempotent — an existing running instance
for the same event + version is returned unchanged. Start audits
`WORKFLOW_INSTANCE_STARTED` (added to `CRITICAL_ACTIONS`). No published
version → 409, unknown template / event → 404. A later publish never touches
a running instance (the instance holds its `template_version_id`, and
migration 0017's freeze trigger keeps that definition immutable — ADR-0005).

#79 (E05-12) operator instance API. `GET /api/v1/events/{id}/workflow`
(`workflows.view`) → `WorkflowEngineService.instance_view`: per function node
`state` (done/active/pending) mirroring the token state, `progress`,
`pending_decisions` (XOR/OR splits with a waiting token and no decision, plus
their branch options), `decisions` made (auto + operator), `started_at` /
`ended_at`, and the instance's audit-event references. Steps carry **no
assignee** — responsibility stays on the whole event. `POST
.../workflow/steps/{node}/complete` and `POST
.../workflow/decisions/{connector}` (`workflows.execute`) drive
`complete_step` / `decide` on the event's running instance and return the
fresh view; out-of-order → 409, bad decision → 422, both idempotent.
`resolve_event_instance` picks the running instance (else the latest).

#80 (E05-13) template-admin API + simulation. `bbz_core.domain.workflow.
simulate.simulate(definition, context=…, decisions=…)` — a pure in-memory
dry-run driving the real engine: operator steps auto-complete, timers
fast-forward, auto actions are recorded as **would-be** outbox rows (never
enqueued), unresolved branches surface as `pending_decisions`. Report:
`status` / `visited_nodes` / `steps` / `decisions` / `outbox_dry_run` /
`pending_decisions` / `active_nodes`. `diff_definitions(before, after)` →
structural node/edge diff (the basis of a changelog). `WorkflowLifecycleService`
gained `create_template` / `rename_template` / `delete_draft_version` (refused
if an instance is pinned) / `simulate_version` / `version_diff`, each audited
(`WORKFLOW_TEMPLATE_CREATED` / `_UPDATED` / `WORKFLOW_SIMULATED`, all in
`CRITICAL_ACTIONS`). API: `GET/PATCH /workflow-templates/{id}`, `DELETE
/workflow-template-versions/{id}`, `POST .../{id}/simulate`, `GET .../{id}/diff`.

**Epic 05 COMPLETE (13/13).**

### Epic 06 – HA Cluster: **COMPLETE (14/14)** — #92 shipped as a scaffold
#81 (E06-01) per-node deployment topology. `deploy/node/` — the full stack for
one BBZ server (`name: bbz-node`): api / web / PostgreSQL+Patroni (Spilo) /
an etcd member / Caddy reverse proxy, with `.env.example`, file-based
`secrets/*.example` (real files gitignored), `patroni/patroni.node.yml`
template, `reverse-proxy/Caddyfile`. `deploy/quorum/` (`name: bbz-quorum`) —
an etcd member **only**, no BBZ services. Settings gained `secrets_dir` (from
`BBZ_SECRETS_DIR`, so `/run/secrets/bbz_jwt_secret` supplies `BBZ_JWT_SECRET`).
CI `compose` job now `docker compose config`-checks all three stacks.
`test_deploy_topology.py` guards the shape (quorum = etcd only, node = full
set, images pinned, no plaintext credentials, no committed secret/.env).
Patroni tuning is #82, the 3-member etcd cluster is #84.

#82 (E06-02) Patroni replication + failover — **ADR-0021 (Accepted)**:
synchronous replication with automatic fallback (`synchronous_mode: true`,
`synchronous_mode_strict: false`, `synchronous_node_count: 1`,
`maximum_lag_on_failover: 1 MiB`). Zero RPO while both DB nodes are healthy; a
lone primary stays writable (degrades to async, logged) rather than blocking —
a Leitstelle must keep taking calls. Timing `ttl 30 / loop_wait 10 /
retry_timeout 10`, target RTO ≤ 60 s. `deploy/node/patroni/patroni.node.yml`
fleshed out (pg_rewind, slots, `synchronous_commit on`), merged into Spilo via
`SPILO_CONFIGURATION`. `docs/runbooks/db-failover.md` rewritten with the
RTO/RPO table + switchover steps. `AuditAction.DB_FAILOVER` added (emitter is
the cluster observer, E06-04/#85). Replication vs superuser creds are separate
secret files. The real primary-kill harness is #92.

#84 (E06-03) etcd 3-member cluster with mutual TLS. `deploy/etcd/`:
`gen-certs.sh` (openssl — CA + per-member peer/server + per-client certs, SANs
from a member table), `bootstrap-auth.sh` (`auth enable`; role `patroni` RW on
`/patroni/`, role `bbz` RW on `/bbz/`, `admin` read-only — users authenticated
by client-cert CN), `snapshot.sh` (backup hook; retention is #95). Both etcd
services (node + quorum) now enforce mTLS on the peer **and** client planes
(`--client-cert-auth` / `--peer-client-cert-auth`, `https://` everywhere), list
all three members, and mount `./etcd/certs`. Patroni talks to etcd over TLS as
user `patroni`; the API over TLS as `bbz-app` — new settings
`cluster_dcs_tls_{ca,cert,key}_file` threaded into the `EtcdLeaderElection`
httpx client (`EtcdTls`). `deploy/**/etcd/certs/` gitignored.
`test_deploy_topology.py` covers the TLS flags, the ACL prefixes, the scripts,
and runs `gen-certs.sh` to verify a CA-signed member/client cert. The
one-member-down harness is #92.

#85 (E06-04) `/cluster/status` real implementation.
`bbz_core.infra.cluster_status.gather_status(session)` probes three sources
and degrades honestly (never a 500): **etcd** — per-endpoint
`/v3/maintenance/status` for `dcs_healthy` + `quorum` (a raft leader visible),
plus a range read of `worker_leader_prefix` for the `leaders` map (and
`control_leader` = `leaders["control_leader"]`); **Patroni REST**
(`patroni_rest_endpoints` setting) — `/cluster` for per-node `db_role` +
`replication_lag_bytes`; **local PostgreSQL** — `pg_is_in_recovery()` + the
receive/replay LSN gap, always representing this node. `last_event_seq` =
`max(domain_events.event_seq)`. The endpoint now returns `stub: false`, is
gated `require("system.cluster.view")` (401/403), and adds a `leaders` field.
No secrets in the body.

#86 (E06-05) `/health/ready` gated on the HA state. `_collect_checks()` now
runs, **in order** (~2 s each): (1) `database` (existing `check_database`),
(2) `cluster` — `cluster_status.local_node_ready()` delegates to this node's
local Patroni `/readiness` (`patroni_local_rest_url` setting; 503 while
creating a replica or lagging past `maximum_lag_on_failover`). No local
Patroni → the check passes (single-node dev). Any failing check → `503
not_ready`. `deploy/node` sets `BBZ_PATRONI_LOCAL_REST_URL` +
`BBZ_PATRONI_REST_ENDPOINTS`; the Caddyfile uses `/health/ready` as its
upstream active health check.

#87 (E06-06) cluster singletons as shared infra. `bbz_core.workers.registry`
declares the named singletons (`outbox-dispatcher`, `workflow-timer`; each a
one-*tick* callable), `bbz_core.workers.manager.ClusterWorkers` starts one
`run_as_singleton` per name in the FastAPI lifespan when
`run_background_workers` is set (default off — tests/CI unaffected; both
composes set it). Every node runs the loop; only the etcd-lease holder ticks;
step-down on renewal failure → failover < 2×TTL; `dedupe_key` / `SKIP LOCKED`
cover the hand-off overlap. `/cluster/status` gains `singletons` (the names)
alongside `leaders` (`name → node_id` from `/bbz/leader/*`).
`docs/ARCHITECTURE_OVERVIEW.md` documents the pattern.

#88 (E06-07) client catch-up protocol. `event_feed` now emits one
`CatchUpComplete(head)` after the `after_seq` backlog is drained (SSE: `event:
caught_up` / `{"head":N}`; WS: `{"type":"caught_up","head":N}`), so a client
that fails over to the other node replays `read_since` and then knows it holds
everything through `head`. `event_log.head_seq(session)` + `GET
/api/v1/events/stream/head` → `{event_seq}` let a client cheaply check if it is
behind (identical on every node once replicated). `event_seq` is documented as
**monotonic but not gapless** — a post-failover jump is a gap, not a loss; the
client tracks "highest seen", never "next expected". `docs/client-catchup.md`
specifies the handshake. Authz is per (re)connect.

#89 (E06-08) quorum node finalised. `deploy/quorum/` etcd service hardened —
`read_only` FS + `tmpfs /tmp`, `cap_drop: [ALL]`, `no-new-privileges`,
`mem_limit`/`cpus`/`pids_limit`, published ports bound via `${QUORUM_BIND}`
not `0.0.0.0`, a local-only `/metrics` listener on `:2381` (the monitoring
stack is Epic 22). `deploy/quorum/HARDENING.md` (compose-enforced +
host-operator checklist) and `docs/runbooks/quorum-node.md` (bootstrap,
verify, replace a failed witness). CI now asserts `docker compose config
--services` on the quorum profile is exactly `etcd`;
`test_deploy_topology.py` checks the hardening flags + the docs exist.

#91 (E06-10) migration strategy — expand/contract (done before #90 as its
dependency). `docs/CONVENTIONS.md` gains the expand → migrate-data → contract
convention + a migration-review checklist; a migration marks its phase in the
docstring (`expand-contract: contract` / `: safe`).
`server/tests/test_migration_safety.py` parses every migration's `upgrade()`
via `ast` and fails on a destructive op (`drop_column/table/constraint`,
`alter_column(nullable=False)`, destructive `op.execute` SQL) without a
marker; it also checks `revision == filename stem`. New CI job
**`migration-compat`**: migrate a fresh DB to the new head, install the
**previous** app version (base sha, own venv), then run
`tools/check_migration_compat.py` — for every table the old ORM maps, a
`SELECT` of all its columns must still succeed (catches drop/rename).

#90 (E06-09) rolling-update mechanism. `tools/rolling-update.sh` (POSIX):
pre-flight (`/cluster/status` `stub:false`/`dcs_healthy`/`quorum`, no node
over the 1 MiB replication-lag limit, `MIGRATION_CHECKED=1`), refuses a
non-digest image, then per node **passive first** — `docker compose pull/up
--no-deps api`, poll `/health/ready` until green (the 503 during boot is the
drain), re-run pre-flight; any failure aborts and leaves later nodes
untouched. `POST /api/v1/system/rolling-update` (`{phase, image, notes?}`,
`require("system.cluster.manage")`) records `ROLLING_UPDATE_STARTED` /
`_COMPLETED` audit markers (both in `CRITICAL_ACTIONS`).
`docs/runbooks/rolling-update.md` rewritten with the order, drain, abort and
rollback steps.

#92 (E06-11) HA failure-scenario harness — **scaffold** (scenarios written to
the shape the HA guarantees require, but not executed end-to-end here).
`deploy/ha-test/`: a single-host mini cluster (`compose.yml` — 2× api, pg1/pg2
Spilo, `pgha` HAProxy routing `:5432` to the current primary, 3× etcd, Caddy
LB) + `lib.sh` helpers + 7 `scenarios/*.sh` (srv01/srv02-down,
db-primary-loss with an RTO check, net-isolation, witness-down,
client-reconnect, recovery) + `run.sh` + `seed.py` + `setup.sh`.
`assert_single_primary` after every fault (split brain = fail).
`.github/workflows/ha-nightly.yml` runs it scheduled, `continue-on-error`
until shaken out on real hardware; `test_ha_harness.py` lints the scripts +
compose + workflow; `.ai/TESTING.md` documents the seven scenarios. The CI
`compose` job now also config-checks `deploy/ha-test`.

#93 (E06-12) reverse-proxy finalised. `deploy/node/reverse-proxy/Caddyfile`:
a `(security_headers)` snippet (HSTS, CSP baseline, X-Content-Type-Options,
X-Frame-Options, Referrer-Policy, Permissions-Policy, COOP, strips
`Server`/`X-Powered-By`), an `(api_upstream)` snippet with `health_uri
/health/ready` + `flush_interval -1` (unbuffered SSE/WS) + `fail_duration`
draining, `@api` routes `/api|/health|/cluster|/ws/*` to the API and the rest
to the SPA, plain HTTP → HTTPS redirect, internal-PKI `tls` line commented for
the operator. The dev-only root `deploy/reverse-proxy/Caddyfile` is trimmed +
labelled. CI validates + fmt-checks all three Caddyfiles;
`test_deploy_topology.py` asserts the header baseline, drain + WS passthrough,
and runs `caddy validate` on each.

#94 (E06-13) HA metrics endpoint. New dep `prometheus-client`.
`bbz_core.infra.metrics` — a dedicated `CollectorRegistry` with
`bbz_cluster_dcs_healthy` / `bbz_cluster_quorum` /
`bbz_cluster_node_is_primary{node}` / `bbz_replication_lag_bytes{node}` /
`bbz_event_seq_head` / `bbz_outbox_pending` / `bbz_worker_leader{singleton}`
(all refreshed on scrape from `gather_status` + a DB read) and
`bbz_stream_connections{transport}` (a live gauge the SSE/WS handlers
`track_inprogress`). `GET /api/v1/system/metrics` (`require
("system.cluster.view")` — not public) renders the exposition; never 500s.
`docs/metrics.md` documents each metric + alerting starting points.

#95 (E06-14) backup / restore. `deploy/backup/` — `common.sh` (gpg
**asymmetric** encrypt/decrypt, retention prune), `pg-backup.sh` /
`pg-restore.sh` (encrypted base backup + integrity check; the intended
production tool is pgBackRest, this is the dependency-light reference),
`etcd-backup.sh` / `etcd-restore.sh` (encrypted snapshot save/restore),
`systemd/` daily+6-hourly timers (the PG unit `ExecCondition`s on Patroni
`/primary`). RPO ≤ `archive_timeout` (PG) / ≤ 6 h (etcd), documented.
`docs/runbooks/restore.md` — the operator procedure for both stores;
`rollback.md` updated. `POST /api/v1/system/backup` (`{phase, kind, notes?}`,
`require("system.cluster.manage")`) audits `BACKUP_COMPLETED` /
`RESTORE_PERFORMED` (both in `CRITICAL_ACTIONS`).
`.github/workflows/backup-nightly.yml` (weekly, non-gating): a real
pg_dump→gpg→restore→count-match round trip + an etcd snapshot save/restore.

**Epic 06 COMPLETE (14/14)** — #92 (HA harness) shipped as a scaffold that
needs a real multi-host runner before its nightly job can gate.

### Epic 07 – Web UI / PrimeVue: **blocked on toolchain (1/19)**
#96 (E07-01) mockup-parity checklist — `docs/mockup-parity-checklist.md`:
every `.ai/FEATURES.md` / §13 feature → the issue that delivers its UI →
status (`todo` / `backend-done` / `done` …). 21 core-UI rows point at Epic 07
(#96–#129, `E07-01`…`E07-19`); telephony / contacts / triggers / video / BKU
rows point at their epics. `server/tests/test_parity_checklist.py` enforces
the issue-ref format, the `E07-xx ↔ #issue` map, valid statuses, and
FEATURES.md coverage.

**#97–#129 are all `Area: frontend` (Vue 3 / PrimeVue / Vitest / Playwright)
and Node/npm is not available in this environment** — the frontend CI job is
also `continue-on-error`. Those need a Node-equipped session. Backend work
continues on Epic 20 in the meantime.

### Epic 20 – Archive / Postprocessing: **backend COMPLETE (8/8; 1 Playwright scaffold)**
- **#414 (E20-01) archive detail model** — decision documented in
  `docs/domain/archive.md`: **no `event_archive` table**; an archived event is an
  `events` row with `status=archived` and all history lives in the same
  append-only tables (ADR-0011). `ArchiveQueryRepository.detail(event_id)`
  (`bbz_core/infra/repositories/archive_queries.py`) bundles event detail +
  `domain_events` + workflow instances (task results, decisions, pinned template
  version) + audit refs + `calls` (reserved, Epic 11). `test_archive_detail.py`
  proves active-vs-archived depth parity.
- **#416 (E20-02) archive list filters** — `GET /api/v1/events` gained optional
  `created_from`/`created_to`, repeatable `priority`, `bbz_id`, `assignee_id`
  (active responsible) filters; keyset cursor unchanged. `queue=active` still
  excludes archived and ignores the filters. `test_archive_list_api.py`.
- **#418 (E20-03) archive detail API** — `GET /api/v1/events/{id}/archive-detail`
  (`events.view`, no audit) renders the E20-01 bundle; every inner list is
  deterministically ordered (`event_seq`, then timestamps asc).
  `test_archive_detail_api.py`.
- **#420 (E20-04) postprocess notes, versioned** — `POST /events/{id}/notes` now
  accepts `kind: postprocess` (works on archived events); new
  `PATCH /events/{id}/notes/{note_id}` writes an append-only new version and
  supersedes the old row (`FOR UPDATE` on the tip; `event_notes.version` /
  `thread_id` / `superseded_by_id` / `edited_by/at`, migration 0022). Add + edit
  each emit a domain event (`EVENT_NOTE_ADDED` / `EVENT_NOTE_UPDATED`, both now
  in the payload schema + catalog) **and** an audit row (both in
  `CRITICAL_ACTIONS`). `GET /events/{id}/notes` returns each thread's current
  version + ordered history; the plain detail shows only the current version.
  `test_postprocess_notes_api.py`.
- **#422 (E20-05) reactivation finalize** — two-step: new
  `POST /events/{id}/reactivation-intent` (`events.reactivate`, 409 unless
  archived) mints a stateless HMAC token bound to `event_id·user_id·version`
  (`bbz_core/api/reactivation.py`, TTL `reactivation_token_ttl_seconds`=300).
  `POST /events/{id}/reactivate` now also requires that `token` (422 on
  mismatch/expiry) on top of `confirm`+`reason`. Accidental-series guard:
  second reactivation of an event within `reactivation_cooldown_seconds`=60 →
  **429** (`RateLimitedError`, `_apply_transition` gained a `precondition` hook).
  Reactivated event re-enters `queue=active`. `test_reactivation_flow_api.py`,
  `test_reactivation_token.py`.
- **#424 (E20-06) export bundle** — `GET /events/{id}/export` now returns the
  complete reproducible record (`bundle_version` "1", `exported_at`, event +
  `domain_events` + `workflows` + full `audit_entries` [event- **and**
  workflow-instance-targeted] + `calls`), deterministically ordered.
  `ArchiveQueryRepository.export_bundle()`. Now requires `events.export` **+**
  `system.audit.view`. `?format=pdf` → dependency-free PDF via
  `bbz_core/api/pdf.py` when `export_pdf_enabled` (else 404). The old lean
  `EventQueryRepository.export()`/`EventExport` were removed.
  `test_event_export_bundle_api.py`.
- **#426 (E20-07) retention policy + no-hard-delete guard** —
  `docs/domain/retention-policy.md` (kept-forever tables vs. prunable derived
  data + windows). Migration 0023 adds a `BEFORE DELETE` trigger
  (`bbz_forbid_row_delete`) on `events` / `event_status_history` /
  `event_notes` (audit/domain already blocked by 0016). Settings
  `retention_completed_command_days`/`_completed_outbox_days`/`_processed_inbox_days`
  for the prunable classes (Epic 22 jobs). `test_no_hard_delete.py` contract
  test: no `bbz_core` delete path and no migration `upgrade()` delete against the
  5 protected tables, and the guard triggers stay defined.
- **#429 (E20-08) archive/postprocessing E2E** — `test_e2e_archive_lifecycle.py`
  walks the whole chain at the API level: work an event + workflow step →
  archive → archive-detail (full depth) → postprocess note add + edit →
  export bundle → two-step reactivation (422 without token) → back in
  `queue=active`; asserts the ordered audit trail and that nothing is
  hard-deleted (3 note rows kept, status history survives archive+reactivate).
  The browser half is scaffolded (`apps/web/e2e/archive-lifecycle.spec.ts`,
  `test.fixme`) pending E07-11/#113 + E07-12/#115. Merged as `Refs #429`.
**Epic 20 done at the backend level** (PRs #576–583).

### Epic 08 – BBZ Desktop Client (Electron): **blocked on toolchain**
All issues need Node/Electron; skipped like Epic 07.

### Epic 09 – BBZ Client Agent (Go): **1/10 (rest blocked on Go toolchain)**
- **#145 (E09-01) ADR-0009 → Accepted** — language decision finalised: **Go**
  for both agents. Shared internal libs named: `discovery` (SRV01/SRV02
  discovery + failover), `outbox` (encrypted cache + offline outbox), and
  `commandenvelope` (typed command envelope, closed type registry, no arbitrary
  exec). Go workspace at `services/bbz-agents/`. E09-02+ need `go` (not
  available here).

### Epic 10 – BKU Agent (Go): **1/16 (schema issues doable; agent needs Go)**
- **#165 (E10-01) bku agent schema** — migration 0024 + `bku_agent.py` model:
  `bku_agents` (agent_id, workplace_id, device_pubkey, generation, status;
  partial unique `one active per workplace`), `bku_agent_enrollments`
  (token_hash unique — hashed only, single-use `used_at`, `expires_at`),
  `bku_agent_commands` (closed `type` CHECK — no arbitrary exec —, status
  CHECK, `expected_generation`, CASCADE from agent). `test_bku_agent_schema.py`.
- **#167 (E10-02) application-catalog schema** — migration 0025 +
  `application_catalog.py`: `application_catalog` (name, url [CHECK
  `~* '^https?://'` — the launch allow-list], `launch_mode` CHECK
  window/app_window/tab, enabled, sort_order, version, icon,
  target_monitor_hint) + `application_catalog_scopes` (app_id CASCADE, optional
  role_key / bbz_id / workplace_id narrowing). `test_application_catalog_schema.py`.
- **#191 (E10-14) BKU permission-seed guard** — the 8 `bku.*` keys + role
  grants were already seeded by 0008 (generic `CATALOG`/`BUILTIN_ROLES`);
  `test_bku_permissions_seed.py` now locks the policy: `bku.session.logout` /
  `bku.device.restart` are Administrator/Sichtleiter only, Nur-Lesen at most
  `status.view`/`catalog.view`, no role grants an unknown `bku.*` key.
  `docs/domain/permission-catalog.md` documents the default grants.

**Epic 10: 3/16 doable here (E10-01/02/14).** E10-03+ (enrollment, command bus,
agent, UI) need the Go toolchain / identity lib.

### Epic 11 – Telephony Core: **in progress (12/16)**
- **#197 (E11-01) telephony core schema** — migration 0026 + `telephony.py`:
  `lines` (provider+external_id unique, state CHECK), `calls` (`bbz_call_id`
  unique + **independent of** `source_call_id`; `direction`/`state` CHECK — the
  E11-04 state machine + `ended_pending_documentation` for the E11-10 hangup
  guard), `call_participants` (role CHECK, CASCADE), `call_documentation`
  (PK = `call_id` → one per call, `category` CHECK nullable-until-set §13.10,
  `mandatory_done`). `test_telephony_schema.py`.
- **#199 (E11-02) telephony provider protocol** — the `bbz_integration_sdk`
  `TelephonyProvider` protocol is finalised: all 14 §8.12 methods, fully typed
  with new vendor-neutral payload models in
  `providers/telephony_types.py` (`LineInfo`, `CallSnapshot`,
  `CallEvent` [mirrors `telephony_event.v1.json`], `CommandAccepted`,
  `CallerResolution`, `ReconcileResult`, enums). `TELEPHONY_METHODS` /
  `TELEPHONY_CAPABILITIES` constants. `mypy --strict` clean.
  `packages/integration-sdk/tests/test_telephony_protocol.py` is the conformance
  test (method set, full annotations, schema-field parity, mock satisfies it).
  The mock still returns dicts — E11-05 makes it return the typed models.
- **#201 (E11-03) telephony event ingestion → inbox → dedupe** —
  `bbz_core/infra/telephony_ingest.py`: validates against `telephony_event.v1`
  (`additionalProperties:false` → a vendor field is a reject), dedupes via the
  E04-07 provider inbox on `(provider, source_call_id, event_type)` for call
  events (so a reconnect replay processes once) / `telephony_event_id` for
  line/CTI events, then calls a registered `set_call_event_dispatch` hook
  (E11-04 wires the call aggregate). `POST /api/v1/telephony/events` gated by the
  new **M2M** permission `calls.ingest_provider_events` (`MACHINE_KEYS` — never
  in a human built-in role; admin/sichtleiter globs now use `_HUMAN_KEYS`).
  `test_telephony_ingest_api.py`.

- **#203 (E11-04) call aggregate & lifecycle** — pure
  `bbz_core/domain/telephony/` (`CallState`/`CallDirection`, `CallAggregate`,
  `provider_target_state` / `business_event_for`): normalized provider events
  drive the state machine (offered→ringing→connected→held↔connected→
  disconnected/failed), out-of-order / post-terminal / unknown events are
  absorbed without raising. `CallLifecycleService` (`infra/repositories/
  call_lifecycle.py`) resolves-or-creates the `calls` row with a stable
  `bbz_call_id` (`CALL-YYYYMMDD-XXXXXXXX`), persists state + `started_at`/
  `ended_at`, records participants, and appends + audits the business events
  `CALL_RINGING`/`CALL_ANSWERED` (first connect only) /`CALL_ENDED` (new in the
  payload schema, catalog, `AuditAction` + `CRITICAL_ACTIONS`). Wired as
  `telephony_ingest`'s dispatch hook in `create_app`.
  `test_call_aggregate.py` (transition matrix + chaos), `test_call_lifecycle_api.py`.

- **#205 (E11-05) full `telephony_mock`** — `MockTelephonyProvider` now
  implements the whole protocol with the E11-02 typed models and a driveable
  `asyncio.Queue` event stream (`drain_events()`). Scenario helpers:
  `simulate_incoming` (known/unknown caller), multiple waiting calls,
  answer/hangup/hold/resume/**transfer** (2 events, requires destination)/
  **conference**, `send_dtmf` (profile only, never the code), `resolve_caller`
  (directory), `simulate_provider_out/in_service`, `replay_backlog` (reconnect).
  Commands idempotent on `command_id`. Manifest capabilities + config
  (`directory`) expanded. `integrations/telephony_mock/tests/test_mock_provider.py`.

- **#207 (E11-06) call control API** — `bbz_core/integrations_host/providers.py`
  loads an adapter **dynamically** (`importlib`, so no static `bbz_core →
  integrations` import) and caches the active telephony provider as a process
  singleton (`active_telephony_provider()`, `reset_provider_cache()` for tests;
  setting `telephony_integration_id` = `telephony_mock`). `api/v1/calls.py`:
  `POST /calls/{id}/answer|hangup|hold|resume|transfer` + `POST /calls/dial`,
  each `require("calls.<verb>")` (resume shares `calls.hold`), command-envelope
  idempotent (a repeated `X-Command-Id` replays and never re-hits the provider),
  audited `CALL_CONTROL_ACTION` (new `AuditAction` + `CRITICAL_ACTIONS`).
  Transfer needs a non-empty destination (422); a call with no `source_call_id`
  yet → 409. `test_call_control_api.py`.

- **#209 (E11-07) line status API** — `LineStatusService`
  (`infra/repositories/line_status.py`, run alongside the call lifecycle from the
  same dispatch hook) upserts the `lines` row from `LINE_IN_SERVICE` /
  `LINE_OUT_OF_SERVICE` events and appends a `LINE_*` domain event (schema +
  catalog; not audited) on a real change only. `GET /api/v1/lines`
  (`calls.view`, optional `?provider=`). `test_line_status_api.py`.

- **#213 (E11-09) mandatory call documentation** — `PUT /calls/{id}/documentation`
  (`calls.document`) upserts `call_documentation` (one row per call, last-write
  wins). `category` is the §13.10 `CallCategory` enum → 422 on an unknown value;
  `free_text` optional. `CALL_DOCUMENTED` domain event + mandatory audit fire
  only once a category is set (`mandatory_done`); free-text-only saves persist
  silently. `GET /calls/{id}/documentation` (`calls.view`).
  `test_call_documentation_api.py`.

- **#215 (E11-10) hangup guard** — `POST /calls/{id}/hangup` without a
  documentation category leaves the call in `ended_pending_documentation` (the
  connection is down but the call is *not* closed — no `CALL_ENDED` yet).
  `_control` gained a `finalize` hook that runs in the state transaction;
  `_finalize_ended` appends + audits `CALL_ENDED` once. `PUT
  /calls/{id}/documentation` with a category on a pending call closes it
  (`CALL_DOCUMENTED` then `CALL_ENDED`, state `disconnected`). Hangup with a
  category already set closes immediately. `GET /calls/pending-documentation`
  (`calls.document`) lists the open obligations, oldest first. No bypass —
  server-enforced. `test_call_hangup_guard_api.py`.

- **#217 (E11-11) call-history API** — `GET /api/v1/calls`
  (`calls.view_history`, personenbeziehbar) returns the call history newest
  first. `CallQueryRepository` (`infra/repositories/call_queries.py`): keyset
  pagination on `(created_at, id)` desc (deterministic, stable under inserts),
  filters `direction` / `state` / `number` (exact match on a participant) /
  `category` (`call_documentation`) / `since` / `until` (on `created_at`,
  inclusive). Each item carries participants + `category` + `has_free_text`.
  Read-only — no audit event, no schema change. Scope-filter is a no-op hook
  until E23 (same as the event queries). `test_call_history_api.py`.
- **#211 (E11-08) caller resolution** — migration 0029 adds
  `calls.caller_contact_id` (FK→contacts SET NULL) + `calls.caller_priority`
  (CHECK low|medium|high). `CallLifecycleService._resolve_caller` snapshots the
  calling party's contact + priority via `ContactMatcher` (E14-04) on every
  inbound event while still unresolved — a contact added mid-call is picked up
  on a later event (so `ContactMatcher` no longer caches *negative* results).
  NULL contact = "unknown". Outbound calls are not caller-resolved. Silent — no
  audit, no domain event. `test_caller_resolution.py` (integration via the
  ingest path).
- **#219 (E11-12) waiting-call queue** — `GET /api/v1/calls/ringing`
  (`calls.view`) returns calls in `offered`/`ringing` ordered by caller
  priority (`_PRIORITY_RANK` case: high→medium→low→unknown) then waiting time
  (`coalesce(started_at, created_at)` asc). Unpaginated. `CallHistoryItem` /
  `CallHistoryItemOut` gained `caller_contact_id` + `caller_priority` (also
  surfaced in the history list). The telephony ingest endpoint now calls
  `notify_event_appended()` on a *new* event so `GET /events/stream` wakes and
  a client re-fetches the queue promptly (the call transition is already a
  domain event on the log). `test_call_queue_api.py`.

**Next:** Epic 11 backend is done — **E11-13/14/15 (UI), E11-16 (Playwright)**
are frontend/E2E → blocked. Epic 07 / 08, #92, the Go agents (09/10 impl) and
the #429 browser E2E stay blocked on a Node / Go / multi-host session.

### Epic 12 – CUCM / JTAPI: **blocked**
All 20 issues are the separate Java `services/cucm-cti-gateway` and hinge on
`jtapi.jar` + real CUCM §8.18 data — no Java toolchain here, no invented Cisco
API. `integrations/telephony_cucm/` stays a placeholder README.

### Epic 13 – SIP Telephony: **1/8 (rest needs a SIP stack / test PBX)**
- **#269 (E13-01) `telephony_sip` scaffold** — `integrations/telephony_sip/`:
  `manifest.json` (domain `telephony`, capabilities answer/dial/hangup/hold/
  resume/transfer/send_dtmf/monitoring, `mock:false`), `config_schema.json`
  (gateway `asterisk_ari|freeswitch_esl`, `credentials_secret_ref`,
  `dtmf_transport`), and `adapter.py` — a `SipTelephonyProvider` that satisfies
  the full `TelephonyProvider` protocol: lifecycle + read queries give safe
  empty/unknown values (health = `unknown`), every control command raises
  `SipNotConfiguredError` until E13-03+. New import-linter contract
  *"telephony_sip is independent of Cisco CUCM / JTAPI"* (`root_packages` gained
  `integrations`). `integrations/telephony_sip/tests/test_sip_scaffold.py`.
- Next: E13-02 (ADR-0023 Asterisk vs FreeSWITCH + test gateway), E13-03..08
  (SIP adapter, events, control, DTMF, secrets, PBX integration tests) — need a
  SIP stack / containerized test PBX.

### Epic 14 – Contacts / Call Priorities: **backend COMPLETE (6/10; E14-07..10 frontend)**
- **#285 (E14-01) contacts schema** — migration 0027 + `contacts.py`:
  `contacts` (name, org, notes, `quick_dial`, `bbz_id` scope — plain UUID like
  `events.bbz_id`), `contact_numbers` (`e164` stored normalized — a CHECK
  enforces `^\+[1-9][0-9]{1,14}$`; `unique(contact_id, e164)`; `is_primary`;
  CASCADE), `contact_priorities` (PK = `contact_id` → one current row per
  contact, `priority` `low|medium|high` CHECK, `set_by`→users SET NULL,
  `set_at`; change history lives in `domain_events` via E14-03). Migration
  up/down/up verified on real PG. `test_contacts_schema.py`.
- **#287 (E14-02) contacts CRUD API** — migration 0028 adds `contacts.deleted_at`
  (soft-delete) + `pg_trgm` GIN indexes on `name`/`org` + a btree on
  `contact_numbers.e164` (`pg_trgm` also added to the conftest `db` fixture).
  `ContactRepository` (`infra/repositories/contacts.py`): CRUD, `search` (name /
  org substring + number, alphabetical, keyset-paginated on `(lower(name), id)`,
  soft-deleted excluded), numbers sub-resource with primary-demotion. `GET/POST
  /api/v1/contacts`, `GET/PATCH/DELETE /api/v1/contacts/{id}`, `…/numbers`
  sub-resource. `POST` carries the command envelope + `idempotent()`; every
  change audits `CONTACT_CREATED`/`UPDATED`/`DELETED` (new `AuditAction` +
  `CRITICAL_ACTIONS`). The `CONTACT_CREATED` domain event + field-level
  audit-diff are E14-05. `test_contacts_api.py`.
- **#289 (E14-03) priority assignment** — `PUT /api/v1/contacts/{id}/priority`
  (`contacts.assign_priority`). `ContactRepository.set_priority` upserts
  `contact_priorities`; assigning the level the contact already has is a no-op
  (`changed: false`, no event, no audit). A real change emits exactly one
  `CONTACT_PRIORITY_CHANGED` domain event (new payload sub-schema: `contact_id`,
  `from` [null on first assignment], `to`, `actor_id`; + event-catalog row) and
  one audit entry with before/after, `event_seq_ref` linked. New `AuditAction`
  in `CRITICAL_ACTIONS`. `test_contact_priority_api.py`.
- **#291 (E14-04) number→contact matching** — pure `bbz_core.domain.contacts`
  (`normalize_number`): DE-centric E.164 rules (`+49…` / `0049…` / `0…` trunk;
  a bare ≤6-digit block is a PBX extension; no country-code guessing, never
  raises — no external phone-number lib). `ContactMatcher`
  (`infra/repositories/contact_matching.py`): exact / base-plus-extension
  (prefix) / digit-suffix match against live contacts' numbers, longest wins,
  a tie across contacts → `ambiguous` (= unknown). 30 s per-process TTL cache
  (`clear_matcher_cache()` wired into the conftest reset). No endpoint / audit /
  permission — E11-08 (caller resolution) is the consumer.
  `test_phone_number_normalization.py` (31-case matrix), `test_contact_matching.py`.
- **#293 (E14-05) contact events + audit wiring** — every contact CUD now emits
  one domain event **and** one audit row, linked by `event_seq_ref`:
  `CONTACT_CREATED` (POST), `CONTACT_UPDATED` (PATCH + each number op, payload
  `changes = {field: {from, to}}` / `{numbers: {…}}`), `CONTACT_DELETED`
  (DELETE). New payload sub-schemas + event-catalog rows. A no-op PATCH (no
  effective field change) emits nothing. `test_contact_events.py` is the
  contract test.
- **#295 (E14-06) quick-dial list** — `GET /api/v1/contacts?quick_dial=true`
  (`contacts.view`) filters the phone-book search to `quick_dial` contacts only;
  `?quick_dial=false` the complement, omitted = all. Same alphabetical keyset
  order (stable). The flag itself is set via `PATCH /contacts/{id}` (E14-02).
  `test_contact_quickdial_api.py`.
- **E14-07..10 are frontend → blocked.** Epic 14 backend is done bar the UI.
  **E11-08 is unblocked** (has `ContactMatcher`).

### Epic 15 – Technical Endpoints / Trigger Engine: **15/15 backend done** (E15-14 frontend → Epic 07)
- **#305 (E15-01) technical-endpoints schema** — migration 0030 +
  `technical_endpoints.py` (MASTER_PROMPT §29 — **not** modelled as contacts):
  `technical_endpoints` (name, site, `type` `door_station|bma|panic_button|
  video_alarm|alarm_dialer|custom` CHECK, `provider_id`, `external_source_ids`
  JSONB, `default_priority` `critical|high|medium|low` CHECK nullable,
  `popup_profile`, `escalation_profile`, `workflow_selection_policy` JSONB,
  `enabled`, `active_config_version`), `technical_endpoint_numbers` (endpoint_id
  CASCADE, `calling_pattern` / `called_pattern` / `cti_route_point`). No FK to
  `contacts`. Migration up/down/up verified on real PG.
  `test_technical_endpoints_schema.py`.
- **#307 (E15-02) trigger-rules schema** — migration 0031 + `trigger_rules.py`:
  `trigger_rules` (name, `endpoint_id`→technical_endpoints SET NULL, `lifecycle`
  `draft|validated|published|retired` CHECK, `priority`),
  `trigger_rule_versions` (rule_id CASCADE, `version_no` unique-per-rule,
  `conditions` JSONB DSL, `actions` JSONB list, lifecycle, `published_at/by`) —
  a **published** version is frozen by a `BEFORE UPDATE` trigger
  (`bbz_forbid_published_trigger_change`, mirrors the workflow one) that blocks
  `conditions`/`actions` changes but lets `lifecycle` move, `trigger_executions`
  (`provider_event_id`→provider_event_inbox, `rule_version_id`, `action_index`,
  `status` CHECK, `result` JSONB; **UNIQUE(provider_event_id, rule_version_id,
  action_index)** = the engine's exactly-once key, E15-09). Migration up/down/up
  verified on real PG. `test_trigger_rules_schema.py`.
- **#309 (E15-03) outbox action types + client_popup_events** — migration 0032
  adds `client_popup_events` (workplace_id NOT NULL, `kind`, `payload` JSONB,
  `expires_at` NOT NULL, `delivered_at`, `dismissed_at`) — a popup is bound to
  one workplace, never broadcast (MASTER_PROMPT §34). The outbox `action_type`
  vocabulary is a free string at the DB level, so the "extension" is a code
  enum: `bbz_core.domain.triggers.TriggerActionType` (create_event,
  attach_workflow, show_client_popup, notify, integration_action, open_camera,
  open_camera_group, answer_call, send_dtmf_profile, hangup_call,
  launch_catalog_app) split into `TRANSACTIONAL_ACTION_TYPES` (create_event /
  attach_workflow) and `OUTBOX_ACTION_TYPES` (the rest); `outbox_action_type()`
  validates. `test_trigger_actions.py`, `test_client_popup_events_schema.py`.
- **#311 (E15-04) normalized inbound signal** — `inbound_signal.v1.json`
  (`additionalProperties:false` at every level — vendor isolation): `signal_type`
  (`CALL_RINGING`/`ANSWERED`/`ENDED`, `TECHNICAL_ALARM_RAISED`,
  `PANIC_ALARM_RAISED`, `DOORBELL_RINGING`, `BMA_ALARM_CALL`), `provider`,
  timestamps, `source{ani,dnis,cti_route_point,technical_endpoint_id,
  external_source_id,site,direction,call_state,alarm_subtype,severity}`. Pure
  `bbz_core.domain.triggers.signals`: `from_telephony_event()` (allowlist-only
  mapper, drops vendor fields), `validate_inbound_signal()`. Thin infra hook
  `bbz_core.infra.inbound_signals.record_inbound_signal()` → E04-07 provider
  inbox (dedupe before rule eval). `bbz_event_schemas.inbound_signal_schema()`.
  `test_inbound_signals.py`, `test_inbound_signal_schema.py`.
- **#313 (E15-05) trigger-rule conditions + selection** — `bbz_rule_dsl` already
  ships `TRIGGER_CONTEXT` (E05-02 typed allowlist) + `parse`/`evaluate`. New
  pure `bbz_core.domain.triggers.rules`: `validate_conditions()` is the publish
  gate (`TRIGGER_CONTEXT.validate` → `RuleConditionError` on an unknown field or
  type-incompatible operator), `signal_to_context()` flattens an inbound signal
  to the DSL context (`ani`→`calling_number`, `severity` string→numeric rank),
  `rule_matches()` / `select_matching_rules()` (matches ordered by
  `(priority, rule_id)` — deterministic on multi-match). `test_trigger_rules_dsl.py`.
- **#315 (E15-06) core typed actions** — `TriggerActionService.run_rule_version`
  runs a published rule version's ordered `actions` against a signal. **Exactly-
  once**: each `(provider_event_id, rule_version_id, action_index)` is claimed in
  `trigger_executions` before the action runs — a replay runs nothing. Handlers:
  `create_event` (EventAggregate + EventRepository, `source="trigger"`),
  `attach_workflow` (`WorkflowEngineService.start_for_event` — idempotent),
  `show_client_popup` (one `ClientPopupEvent` bound to a workplace), `notify`
  (one `external_action_outbox` row). Each action + its ledger row + its
  `TRIGGER_EXECUTED` audit is one transaction; a later action failing doesn't
  un-do an earlier one; a malformed / unknown-template action is recorded
  `failed`. New `AuditAction.TRIGGER_EXECUTED` in `CRITICAL_ACTIONS`.
  `EventAggregate` gained `source` (now persisted); `EventRepository.add` /
  `EventAggregate.create` `actor_id` widened to `| None` (system-raised events);
  `EVENT_CREATED.actor_id` payload accepts `null`. `test_trigger_actions_core.py`.
- **#319 (E15-08) telephony trigger actions** — `answer_call` /
  `send_dtmf_profile` / `hangup_call` handlers in `TriggerActionService`: each
  enqueues **one** `external_action_outbox` row (`action_type` = the value)
  against the active provider, keyed by the `trigger_executions` claim +
  the outbox `dedupe_key` (exactly-once per execution key). `send_dtmf_profile`
  carries `dtmf_profile_id` **only** — a `code`/`dtmf` key in the action is
  rejected outright, the raw code never touches the payload or the audit
  (ADR-0004 / §30). `call_id` comes from the action or the signal's
  `source.source_call_id` (added to `inbound_signal.v1.json` +
  `from_telephony_event`). `test_trigger_actions_call.py`.
- **#317 (E15-07) camera / integration trigger actions** — `open_camera`
  (`camera_ref`), `open_camera_group` (`camera_refs` or `camera_group_ref`) and
  the generic `integration_action` (`capability` + `params`) handlers in
  `TriggerActionService._integration_action`: each enqueues **one**
  `external_action_outbox` row keyed by the same `trigger:{provider_event_id}:
  {rule_version_id}:{index}` dedupe key (exactly-once, no double open). The
  payload carries **only** normalized handles — no vendor object id. A missing /
  malformed camera ref is recorded `failed` and **never** rolls back an earlier
  `create_event` / popup (MASTER_PROMPT §31/§36). All three added to
  `SUPPORTED_ACTION_TYPES` + `_action_config_problems` (publish gate). The outbox
  **dispatch** handler that reaches the `video.*` provider is **E16-08**.
  `test_trigger_actions_camera.py`.
- **#320 (E15-09) rule-execution engine** — `bbz_core.infra.repositories.
  trigger_engine`: after the E04-07 inbox has deduplicated a normalized inbound
  signal, `TriggerEngine.process_inbox_event(inbox_id)` loads every **published**
  rule + its highest published version, `select_matching_rules` orders the
  matches deterministically by `(priority, rule_id)` (E15-05), and each rule
  version's actions run through `TriggerActionService` (E15-06/08) where every
  `(provider_event_id, rule_version_id, action_index)` is claimed once — then the
  inbox row is marked processed. **Exactly-once, active/active**: a
  double-delivered provider event is a duplicate at the inbox (row already
  processed → no-op); a crash mid-sequence leaves the row unprocessed and
  `resume_unprocessed()` re-runs it — every already-done action is a claimed
  no-op, so nothing duplicates. Module fn `process_signal(session, *, signal,
  provider_event_id, dedupe_key)` = record (dedupe) + process, the convenience an
  integration edge calls. `EngineResult(inbox_id, signal_type, matched_rules,
  processed, actions)`. A non-signal inbox row (no `signal_type`) is marked
  processed with 0 matches. Audit: `TRIGGER_EXECUTED` per action (via
  `TriggerActionService`). `test_trigger_engine.py`.
- **#322 (E15-10) trigger-admin API** — two routers + two services, both
  gated `technical_endpoints.view` (read) / `technical_endpoints.manage` (write),
  everything audited (highly privileged — a published rule opens doors):
  - `/api/v1/technical-endpoints` CRUD (`TechnicalEndpointService`): create /
    list / get / patch / delete an endpoint + its telephony number patterns
    (nested, replace-all on patch). A patch bumps `active_config_version`; a
    no-op patch does not. Delete is hard (rules' `endpoint_id` is SET NULL,
    numbers CASCADE). Audit `TECHNICAL_ENDPOINT_CREATED/UPDATED/DELETED`.
  - `/api/v1/trigger-rules` + `/api/v1/trigger-rule-versions/{id}/…`
    (`TriggerRuleAdminService`): rule CRUD (+ its v1 draft on create),
    `POST /trigger-rules/{id}/versions` (new draft, `version_no` = max+1),
    `PATCH`/`DELETE` a **draft** version, and the lifecycle
    `draft→validated→published→retired`. `validate` runs the new
    `bbz_core.domain.triggers.publish_blockers` (DSL conditions vs.
    `TRIGGER_CONTEXT` + every action typed & currently-runnable + ≥1 action + a
    `send_dtmf_profile` `code`/`dtmf` key rejected, ADR-0004); `publish` refuses
    an un-validated version, retires the rule's prior published version and
    mirrors `published` onto the parent rule (engine E15-09 reads that);
    `retire` flips the rule back to `retired` when nothing published remains. A
    published version is immutable — the service refuses the edit and the 0031
    DB trigger is the backstop; a rule with a published version can't be deleted.
    New `domain.triggers` exports `publish_blockers` / `validate_actions` /
    `SUPPORTED_ACTION_TYPES`. Audit `TRIGGER_RULE_CREATED/UPDATED/VALIDATED/
    PUBLISHED/RETIRED`. `test_technical_endpoints_api.py`,
    `test_trigger_rules_api.py`.
  - **Note:** `test_authz_dependency.test_every_api_v1_write_route_declares_a_
    permission` went vacuous when FastAPI 0.141 made `include_router` lazy
    (`_IncludedRouter` — `create_app().routes` no longer exposes flat
    `APIRoute`s). Not fixed here; E15-10's own 403-without-permission tests cover
    the new routes. Worth a `fix(tests)` pass to walk `original_router`.
- **#324 (E15-11) simulation / test mode** — `POST /api/v1/trigger-rules/simulate`
  (`technical_endpoints.manage`, declared before the `{rule_id}` routes) →
  `TriggerEngine.simulate(signal)`: validates the synthetic signal
  (`inbound_signal.v1`), selects the matching **published** rules
  (`select_matching_rules`, same path as the live engine) and reports each rule
  + the actions it *would* run — **no real effect**: no inbox row, no
  `trigger_executions`, no outbox, no event, no DTMF, only one `TRIGGER_SIMULATED`
  audit row. Every reported action is scrubbed of `code`/`dtmf` keys defensively
  (a published version can't carry them — E15-10 gate — but the report never
  echoes a secret). `SimulationReport(signal_type, matched[], planned_action_count,
  executed=False)`. `test_trigger_simulation_api.py`.
- **#326 (E15-12) unmapped-source queue + diagnostics** — migration **0033**
  `unmapped_signals` (dedupe_key UNIQUE, provider, signal_type, source JSONB,
  sample JSONB, occurrences, first/last_seen_at, resolved_at/by/endpoint_id,
  note). When the engine (E15-09) matches a **valid** signal to **no published
  rule**, `record_unmapped()` upserts a row (bumps `occurrences` +
  `last_seen_at`) — never an error, processing still completes and the inbox row
  is marked processed. `bbz_core.infra.repositories.unmapped_signals`:
  `unmapped_dedupe_key()` (provider + type + a fingerprint of the source
  identifiers), `UnmappedSignalService.list_queue / resolve / diagnostics`. API
  (`trigger_diagnostics.py`, prefix `/trigger`): `GET /api/v1/trigger/unmapped`
  (`?include_resolved`), `POST /api/v1/trigger/unmapped/{id}/resolve`
  (`{endpoint_id?, note?}` — binds the source to a technical endpoint or just
  dismisses; audit `TECHNICAL_ENDPOINT_MAPPED`), `GET /api/v1/trigger/diagnostics`
  (open / resolved / total_occurrences / open_by_signal_type). Reads
  `technical_endpoints.view`, resolve `technical_endpoints.manage`. Migration
  up/down/up verified on real PG. `test_trigger_unmapped_queue.py`.
- **#329 (E15-13) BMA flow** — no new production code; `test_bma_flow.py` is the
  automated §35-BMA scenario proving E15-04/06/09 + E03-15 + E05 compose: a
  `BMA_ALARM_CALL` from the configured number (`called_number == "112"` rule
  condition, endpoint type `bma`) → the rule's `create_event` (critical, status
  `new`, `source="trigger"`) + `attach_workflow` → **exactly one** critical
  event with the **current published** workflow version bound
  (`WorkflowInstance.template_version_id`), one `EVENT_CREATED` in `domain_events`,
  two `TRIGGER_EXECUTED` audit rows; the event raises `GET /events/priority-alert`
  (`active:true`) until accepted; a duplicate provider event (`provider_event_id`)
  produces no second event / instance; a call to an unconfigured number creates
  nothing (and lands in the E15-12 unmapped queue).
- **CI billing block (2026-08-31):** GitHub Actions fails every job instantly —
  account payment / spending limit ([[ci-billing-block-2026-08]]). E15-12 (#617)
  and later work are code-complete + locally verified (container runner +
  `alembic up/down/up` on real PG) but **cannot merge** until the user fixes
  Billing & plans. Stacked branches: `feature/326-…` (E15-12) →
  `feature/329-bma-flow` (E15-13) → …
- **#331 (E15-14) client-popup delivery — BACKEND SLICE ONLY** (UI + keyboard +
  Playwright = Epic 07, still blocked). `_show_client_popup` (E15-06) now also
  `append_event`s a **`CLIENT_POPUP_RAISED`** domain event (new sub-schema in
  `event.payloads.v1.json`: `popup_id, workplace_id, kind, expires_at`,
  no secrets) inside the same atomic tx, and `_run_atomic` fires
  `notify_event_appended()` for it — so a connected client catches it on the SSE
  stream (E03-13) + catch-up. New `bbz_core.infra.repositories.client_popups`
  `ClientPopupService.pending_for / mark_delivered / dismiss`. API
  (`client_popups.py`, prefix `/client`, all `events.view`):
  `GET /api/v1/client/popups?workplace_id=…` (live = unexpired + undismissed),
  `POST /api/v1/client/popups/{id}/delivered?workplace_id=…` (idempotent, audit
  `CLIENT_POPUP_DELIVERED` once), `POST .../{id}/dismiss?workplace_id=…`. A popup
  only ever reaches its bound workplace — a mismatched `workplace_id` on an
  action is 403. New `AuditAction.CLIENT_POPUP_DELIVERED` in `CRITICAL_ACTIONS`.
  `test_client_popup_delivery.py`. No migration (`client_popup_events` is E15-03).
- **#333 (E15-15) trigger-engine E2E + ingest wiring** — **ADR-0024**: a
  normalized inbound signal is queued as its **own** `provider_event_inbox` row
  (`signal:` dedupe key) and executed by a new leader-elected singleton
  **`trigger-engine`** (alongside `outbox-dispatcher` / `workflow-timer`) whose
  tick runs `TriggerEngine.resume_unprocessed()`. `ingest_telephony_event`, on a
  new event, maps it with `from_telephony_event` and — if it yields a signal —
  queues that row (`_queue_signal`, best-effort: a mapping failure is logged, not
  raised, so it never breaks call ingestion). `TriggerEngine.process_inbox_event`
  already skips non-signal rows, so the raw telephony rows stay inert to it.
  `test_e2e_trigger_engine.py` walks it end to end at the API level: `POST
  /api/v1/telephony/events` (CALL_RINGING to the BMA number) → one `signal:` row,
  unprocessed → `trigger-engine` tick → exactly one critical event + bound
  workflow version + `EVENT_CREATED` + 2× `TRIGGER_EXECUTED`; a duplicate
  provider event queues no second signal; a failover replay (row reset to
  unprocessed) re-drains without duplicating (the `trigger_executions` claims
  block it).
- **Epic 15 done bar:** E15-14 **frontend** (popup UI, keyboard, Playwright) →
  needs Epic 07. (E15-07 camera/integration actions done — see #317 above.)

### Epic 16 – Coda Video / HxGN dC3 Video: **backend complete (12/13)** — E16-12 (camera UI) → Epic 07
- **#335 (E16-01) `coda_video` scaffold formalised** — the manifest schema gains
  optional `capability_groups` (named, independently-activatable capability sets;
  every grouped capability must also be in `capabilities` — checked in
  `validate_manifest`) and `legacy_display_alias` (display-only superseded name).
  `integrations/coda_video/manifest.json` → v0.1.0, two groups **`video`** +
  **`alarm_ingress`**, `legacy_display_alias: "Cayuga"` (ADR-0016 — `coda_video`
  is the canonical id everywhere). `config_schema.json` gains
  `enabled_capability_groups` (default both). `MockCodaVideoProvider` +
  `build(config)`: `capabilities()` now returns only the enabled groups' caps.
  Still `mock: true` — no vendor API (E16-13). `test_mock_coda.py`,
  `test_manifest_schema.py`.
- **#337 (E16-02) normalized video capability interface** — SDK-level, no vendor
  calls. `bbz_integration_sdk.providers.video_types`: frozen typed result models
  `ResolvedCamera` / `CameraView` / `CameraGroupView` / `AlarmContextView` (only
  normalized `camera_id` handles — no vendor object ids cross the boundary) + the
  error hierarchy `VideoProviderError` → `CameraNotFoundError` / `VideoTimeoutError`.
  `VideoProvider` protocol now fully typed and gains **`focus_camera`**
  (`camera_id, workplace_id, command_id, preset?`); `VIDEO_METHODS`,
  `VIDEO_CAPABILITIES`, new `Capability.VIDEO_FOCUS_CAMERA`. `MockCodaVideoProvider`
  conforms (returns the typed models, `resolve_camera` raises `CameraNotFoundError`
  for an unknown id). `coda_video` manifest gains `video.focus_camera` in the
  `video` group. `test_mock_coda.py`.
- **#339 (E16-03) normalized alarm-ingress capability interface** — SDK-level, no
  vendor calls. `bbz_integration_sdk.providers.alarm_types`: frozen typed models
  `IncomingAlarm` (the alarm as the provider hands it over — identifiers + the
  opaque `raw` dict kept diagnostics-only for the E16-04 hash, never parsed by
  rules) / `AlarmSource` / `AlarmContext` / `ExternalAckResult`; error hierarchy
  `AlarmProviderError` → `AlarmSourceNotFoundError` / `ExternalAckNotSupportedError`;
  `ALARM_INGRESS_CAPABILITIES`. `AlarmIngressProvider` protocol now fully typed
  (`subscribe_alarms → AsyncIterator[IncomingAlarm]`, `resolve_source`,
  `get_context`, `get_associated_cameras`); `ALARM_INGRESS_METHODS`, new
  `Capability.ALARM_GET_ASSOCIATED_CAMERAS`. **External ack is opt-in and a
  separate domain action from the BBZ event ack** — split into its own
  `@runtime_checkable ExternalAckCapable` protocol, present only when the manifest
  declares `alarm.acknowledge_external` (the mock does not). `MockCodaVideoProvider`
  conforms (`simulate_alarm` builds an `IncomingAlarm`, `resolve_source` returns
  `AlarmSource | None`). `coda_video` manifest gains `alarm.get_associated_cameras`
  in the `alarm_ingress` group. `test_mock_coda.py`.
- **#341 (E16-04) alarm normalisation → immutable provider event + inbox dedupe** —
  pure mapper + thin infra hook, mirrors E15-04 telephony. New schema
  `provider_alarm_event.v1.json` (`bbz_event_schemas.provider_alarm_event_schema()`),
  `additionalProperties:false` at every level so a stray vendor key is a
  rejection. `bbz_core.domain.triggers.alarms`: `normalize_alarm_event(dict) → dict`
  allowlist-copies an `IncomingAlarm.model_dump()` into the immutable shape,
  hashes `raw` into `raw_hash` (bare sha256 hex) and **drops the payload**;
  `provider_event_id` is the provider's own id or a deterministic `derived:<sha256>`
  of `source+type+subtype+occurred_at` when it has none; `alarm_event_dedupe_key`.
  `bbz_core.infra.alarm_ingest.ingest_alarm_event(session, dict) → IngestResult`
  runs it through the E04-07 provider inbox — a replayed / dual-node panic alarm
  is stored once (ADR-0006 exactly-once base). **Not** wired to the trigger engine
  yet (E16-07). `test_coda_alarm_normalization.py`, `test_provider_alarm_event_schema.py`.
- **#343 (E16-05) DB schema `integration_camera_mappings`** — migration
  `0034_camera_mappings` + `integration_camera_mappings.py`. A row maps a camera
  to a **technical endpoint** (`endpoint_id`, cascade) OR to an **external alarm
  source** (`alarm_source_external_id`) — CHECK `anchor` needs at least one; both
  at once is allowed. `camera_external_ref` is a normalized handle (no vendor
  object id), `ordinal` orders multi-camera opens, `provider_instance_id` scopes
  it. Admin API is E16-06; the runtime that opens the cameras is E16-07/08.
  Real `alembic up/down/up` verified. `test_integration_camera_mappings_schema.py`.
- **#345 (E16-06) admin config per Coda alarm source** —
  `AlarmSourceConfigService` + `PUT/GET/DELETE /api/v1/coda-alarm-sources/
  {external_source_id}`. A **facade** over E15-10 + E16-05 (no new table): one
  idempotent upsert sets a `provider_id="coda_video"` technical endpoint (name,
  type, site, `default_priority`, popup/EPK/escalation profile, `enabled`) and
  **replaces** the `integration_camera_mappings` rows keyed by that
  `alarm_source_external_id`. `panic_button` → `default_priority` `critical`
  unless the caller overrides (§36). Writes need **both**
  `technical_endpoints.manage` and `integrations.configure`; audited
  `CODA_ALARM_SOURCE_CONFIGURED` / `_REMOVED` (both in `CRITICAL_ACTIONS`).
  `test_coda_alarm_source_admin_api.py`.
- **#347 (E16-07) Coda panic/duress runtime flow (§36.1)** — compose, minimal new
  code. `bbz_core.domain.triggers.from_incoming_alarm(alarm_event) → inbound_signal`
  maps a normalized `provider_alarm_event.v1` (E16-04) to a `PANIC_ALARM_RAISED`
  (subtype `panic_button`) / `TECHNICAL_ALARM_RAISED` signal — allowlisted fields
  only (`external_source_id`, `site`, `alarm_subtype`, `severity` if a BBZ word).
  `alarm_ingest.ingest_alarm_event` now, on a **new** alarm, also queues that
  signal as its own `signal:` provider-inbox row; the `trigger-engine` drain
  worker (ADR-0024) runs it through `TriggerEngine` → matched published rule →
  `create_event`(critical) + `attach_workflow`(published EPK version) +
  `show_client_popup` + `open_camera_group` (decoupled outbox). A duplicate /
  failover alarm dedupes at the inbox → no second event. `test_coda_panic_flow.py`;
  `test_coda_alarm_normalization.py` updated (alarm vs `signal:` rows).
- **#349 (E16-08) camera open as a decoupled outbox side effect** —
  `bbz_core.workers.camera_handlers` (`open_camera` / `open_camera_group`) reach
  the active `video.*` provider (`integrations_host.providers.active_video_provider`,
  new `video_integration_id` setting → `coda_video`). Registered in the
  `outbox-dispatcher` tick. A provider error propagates → dispatcher retries with
  backoff → at `MAX_ATTEMPTS` the row is `failed` (`EXTERNAL_ACTION_FAILED`) **and**
  a `CAMERA_ACTION_FAILED` domain event is appended to the triggering event (new
  `event.payloads.v1` sub-schema) — the event and its popup are untouched
  (MASTER_PROMPT §31/§36). E15-07's camera-action payload gains `command_id` (the
  trigger execution key, passed straight to the provider for idempotency) and
  `event_id`. `test_coda_camera_sideeffect.py`; `test_trigger_actions_camera.py`
  updated for the payload.
- **#351 (E16-09) full `coda_video` mock simulation** — `MockCodaVideoProvider`
  now covers the INTEGRATIONS_CODA_VIDEO.md "Testing" list deterministically:
  panic / intrusion / generic `alarm_type`; `get_associated_cameras` returns the
  alarm's real cameras (`get_context` bundles them); an unmapped source →
  `resolve_source` `None`; a duplicated `provider_event_id`; `reconnect()` replays
  the delivered backlog; `camera_failures` / `fail_cameras()` make a camera's
  open/focus/group raise the new SDK `CameraOpenFailed(VideoProviderError)`.
  `build(config)` + `config_schema.json` gain `camera_failures`. `test_mock_coda.py`.
- **#353 (E16-10) Coda diagnostics API** — `GET /api/v1/integrations/coda_video/
  diagnostics` (`integrations.diagnostics`). `CodaDiagnosticsService` aggregates
  from the provider inbox / outbox: `events_total` / `signals_total`,
  `last_event_at` + `last_event_processing_ms` (`received_at`→`processed_at`),
  `unmapped_total` (`sum(occurrences)` where `provider=coda_video`),
  `last_camera_action_at`, `camera_actions_failed` / `_pending`. The API layer
  adds the provider's own `health()` + `capabilities()` — falling back to
  `state:"unavailable"` when the integration is down, so diagnostics still work.
  No secrets in the body. New `api/v1/integrations.py` router.
  `test_coda_diagnostics_api.py`. (Exact duplicate-hit counter omitted — no
  truthful source; `dedupe_key` is UNIQUE with no hit metric.)
- **#355 (E16-11) Coda-Alarm §36.1 E2E** — `test_e2e_coda_panic.py`, test-only.
  Drives the full stack through the real worker ticks (`cluster_singletons()`
  `trigger-engine` + `outbox-dispatcher`): E16-09 mock panic alarm →
  `ingest_alarm_event` (persist + dedupe) → engine → exactly one critical event +
  current published EPK version + popup + priority-alert (API) → `open_camera_group`
  dispatched against the mock; a monkeypatched failing provider → row `failed` +
  `CAMERA_ACTION_FAILED` on the event, event stays `new`; a duplicate alarm and an
  SRV01-crash replay (`signal:` inbox row reset to unprocessed, re-ticked) → no
  second event / instance / popup. Audit assertions throughout.
- **#359 (E16-13) vendor-integration blocker** —
  [`docs/integrations/coda-video-pending.md`](../docs/integrations/coda-video-pending.md):
  a referenceable "Do NOT invent" list (endpoint URLs, auth, event payloads,
  alarm ack, camera object model, display-agent commands, SDK classes,
  licensing) against writing the real adapter from guesswork (ADR-0006). The
  manifest schema gains an optional `pending_vendor_documentation: list[str]`
  marker; `integrations/coda_video/manifest.json` declares it while `mock: true`.
  `.ai/INTEGRATIONS_CODA_VIDEO.md` links the blocker. `test_manifest_schema.py`.
- **Epic 16 backend complete (12/13).** **E16-12** (camera-view UI) is the only
  open item — needs Epic 07 (E07-08); deferred to the frontend phase.

### Epic 17 – Siedle: **in progress (6/7)**
- **#361 (E17-01) Siedle door-station endpoint profile** — migration
  `0035_door_station_fields` adds `technical_endpoints.dtmf_profile_id` (a
  reference id **only** — the code lives encrypted in `door_action_profiles`,
  E17-02, never here), `popup_text` and `door_open_timeout_seconds` (1–600).
  `TechnicalEndpointService` / the `/api/v1/technical-endpoints` admin API carry
  them; the request models are `extra="forbid"` so a raw `dtmf_code` / `code` /
  `dtmf` key is a 422. Touching a door field, or `type == "door_station"`,
  additionally needs `door.configure` (checked imperatively in the handler, on
  top of `technical_endpoints.manage`; other endpoint types are unaffected).
  Real `alembic up/down/up` verified. `test_siedle_endpoint_profile.py`;
  `test_technical_endpoints_api.py` / `test_trigger_unmapped_queue.py` gain
  `door.configure` where they create door stations.
- **#363 (E17-02) `door_action_profiles` schema — encrypted DTMF** — migration
  `0036_door_action_profiles` + `door_action_profiles` (id, name UNIQUE,
  `dtmf_ciphertext`, `post_dtmf_delay_ms` CHECK 0–10000, `auto_hangup`,
  `created_by`) and the FK from `technical_endpoints.dtmf_profile_id` → it
  (`ON DELETE SET NULL`, also wired into the ORM model). `bbz_core.infra.door_secrets`
  (Fernet, `BBZ_DOOR_DTMF_ENCRYPTION_KEY`, mirrors `auth.totp`; real store is
  ADR-0019 / Epic 23). `DoorActionProfileService` + `/api/v1/door-action-profiles`
  CRUD (`door.configure`): the plaintext code enters once in a POST/PATCH body,
  is encrypted immediately, and is **never** returned (`ProfileOut` has a
  `configured: bool`, no code field), logged, or audited — the audit rows carry
  field **names** only. `resolve_dtmf()` decrypts for the door-open flow (E17-05).
  `TechnicalEndpointService` now rejects an unknown `dtmf_profile_id` (422).
  New `ServiceUnavailableError` (503) → returned when the key is unset. Real
  `alembic up/down/up` verified. `test_door_action_profiles_api.py`.
- **#365 (E17-03) `DOORBELL_RINGING` trigger** — new
  `bbz_core.infra.repositories.endpoint_matcher.match_technical_endpoint`
  (exact match on `calling` / `called` pattern or `cti_route_point`, `enabled`
  + optional `types` filter, lowest-id wins). `telephony_ingest._queue_signal`
  now runs `_resolve_doorbell`: a `CALL_RINGING` signal with no pre-filled
  endpoint whose ANI/DNIS/route matches an enabled `door_station` is re-typed
  **`DOORBELL_RINGING`** with `source.technical_endpoint_id` set, then
  re-validated. An unconfigured number stays `CALL_RINGING` → the engine's
  unmapped-source queue (E15-12). Dedupe unchanged (`telephony_dedupe_key` +
  `signal:` prefix → one signal per telephony event). `test_siedle_doorbell_trigger.py`.
- **#367 (E17-04) klingel popup + decoupled camera** — compose, minimal new code.
  A published rule on `DOORBELL_RINGING` runs `show_client_popup` (bound to the
  workplace, `kind: doorbell`, actions `["open","reject"]`) + `open_camera_group`
  (decoupled outbox, E16-08 — a Coda outage never blocks the popup).
  `TriggerActionService._show_client_popup` now auto-fills `payload.text` from the
  matched door station's `popup_text` ("Klingeln: Haupteingang") when the action
  omits it — no secrets, no schema change. The popup is visible only at its bound
  workplace (`GET /api/v1/client/popups?workplace_id=`). `test_siedle_ring_popup_camera.py`.
  (Playwright leg deferred to the frontend phase / Epic 07, like E15-14.)
- **#369 (E17-05) transactional, idempotent door-open flow** — **ADR-0025**
  (Accepted): BBZ's `door_action_profiles` **is** "the config store" the
  `send_dtmf` protocol note meant; the DTMF **sequence** (not a BBZ id) crosses
  the provider boundary, because an integration can't resolve a BBZ id.
  SDK rename `send_dtmf(dtmf_profile_id=…)` → `send_dtmf(dtmf=…)` (protocol + mock
  + SIP scaffold + tests); the mock no longer echoes the argument.
  `DoorOpenService` + `POST /api/v1/doors/{endpoint_id}/open` (`door.open`,
  idempotent on `X-Command-Id` → replay, **no 2nd open**): loads the door station,
  resolves the profile → digits **transiently** (`resolve_dtmf()`, a local only —
  never persisted / logged / audited), then drives the active telephony provider
  through a persisted `door_open_commands` state machine (`requested → answering
  → connecting → dtmf_sent → completing → done|failed|timed_out`): answer if
  ringing → await CONNECTED (bounded by `door_open_timeout_seconds`) → `send_dtmf`
  **once** (derived `command_id` `door:<cmd>:dtmf` + `dtmf_sent_at` guard) →
  `post_dtmf_delay_ms` → auto-hangup. Every attempt audits `DOOR_OPEN_REQUESTED`
  + `DOOR_OPEN_RESULT` (both critical) with `door_action_profile_id` + outcome,
  never the code. Outcome always reported (HTTP 200): `opened` / `caller_gone` /
  `media_timeout` / `no_dtmf_capability` / `no_profile` / `provider_error` /
  `telephony_unavailable`. Migration `0037_door_open_commands`. Tested against
  `telephony_mock` (real JTAPI/SIP transport is E12-05 / E13-06 — blocked).
  `test_siedle_door_open_flow.py`.
- **#371 (E17-06) audit ohne Klartext-DTMF — redaction net** — new
  `bbz_core.redaction` (stdlib-only leaf): `redacting(<secret>)` registers a
  transient value on a `ContextVar`; `scrub(value)` masks every registered
  substring (`[redacted]`) in str / dict / list / tuple leaves and is a
  same-object no-op when nothing is registered. Wired into **every sink**:
  `AuditService.write` (`before`/`after`/`reason`), `append_event` (`payload`),
  `OutboxRepository.enqueue`/`mark_dispatched`/`mark_retry`/`mark_failed`
  (`payload`/`result`/`error`), and a `_redact` structlog processor (before the
  renderer). `DoorOpenService._drive` runs under `with redacting(digits)` and
  scrubs the returned `detail` — so a telephony provider that echoes the DTMF in
  an exception message cannot leak it to any row or log. `test_siedle_audit_no_dtmf.py`
  (6): `scrub`/`redacting` behaviour, the log processor, and a full door-open
  against a **code-echoing** provider → the sentinel appears in no `audit_events`
  / `domain_events` / `external_action_outbox` row, `door_action_profile_id`
  still present in `DOOR_OPEN_RESULT`.
- **#373 (E17-07) Siedle failure matrix + permissions-seed + §35 E2E** — the
  `door.*` / `technical_endpoints.*` catalog was already seeded by `0008` (it
  iterates `CATALOG` / `BUILTIN_ROLES`); `test_siedle_door_permissions_seed.py`
  locks the policy (open is an operator action, `door.configure` /
  `technical_endpoints.manage` senior-only, read-only can at most look, the seed
  actually wrote the grants). New: **answering a still-ringing doorbell call
  needs `door.answer`** — the API resolves it imperatively and passes
  `may_answer` to `DoorOpenService`; a ringing call without it →
  `answer_forbidden` (HTTP 200, no DTMF). Failure matrix now: `caller_gone` /
  `media_timeout` / `no_dtmf_capability` / `no_profile` / `provider_error` /
  `telephony_unavailable` / `answer_forbidden` — every one a clear result, no
  silent retry (`send_dtmf` fires once via the derived `command_id` +
  `dtmf_sent_at` guard). `test_e2e_siedle_doorbell.py` — the §35 10-step flow
  end-to-end (call → `DOORBELL_RINGING` → camera + popup → open → answer → DTMF
  once → auto-hangup → audit sans code → duplicate event / repeated command open
  once) + a Coda-outage variant (camera row `failed`, the open still succeeds).
- **Epic 17 complete (7/7).** Siedle door communication over telephony/DTMF is
  done end-to-end against the mocks; the real CUCM/SIP `send_dtmf` transport is
  E12-05 / E13-06 (blocked).

### Epic 18 – DWD Weather: **in progress (9/10)**
- **#375 (E18-01) `integrations/dwd` scaffold + manifest + config** — **ADR-0026**
  (Accepted; amended in E18-02 — warnings feed → DISTRICT) pins the three public
  DWD Open Data services: warnings → CAP 1.2
  feed `opendata.dwd.de/weather/alerts/cap/DISTRICT_DWD_STAT/`;
  radar → GeoServer WMS `maps.dwd.de/geoserver/dwd/wms`
  (`dwd:Niederschlagsradar`, rendered frames); observations → POI CSV
  `opendata.dwd.de/weather/weather_reports/poi/`. Degradation contract: a
  fetch/parse failure serves the last good cache + health `degraded`, never
  raises. `integrations/dwd/` — manifest (`domain: weather`, 3 capability groups,
  `mock: false`, `pending_vendor_documentation: []` — DWD is documented),
  `config_schema.json` (`region`, `places[]` = `{name, warncell_id,
  poi_station_id}`, per-service base-url/refresh, `enabled_capabilities`),
  `DwdWeatherProvider` stub (lifecycle real; `get_warnings`/`get_radar_frames`/
  `get_observations` raise `DwdNotImplementedError` until E18-02/03/04). Target
  places Nürnberg / Fürth / Erlangen / Schwabach / Ansbach / Neustadt a.d. Aisch.
  `test_dwd_scaffold.py`. Discovery + `/api/v1/meta` pick it up.
- **#383 (E18-05) DB schema `weather_alerts` / `weather_observations`** — migration
  `0038_weather_schema` + `bbz_core.infra.models.weather`. `weather_alerts`
  (region, type, level, valid_from/to, headline, description, source_ref,
  received_at) UNIQUE `(source_ref, region)` — a CAP alert covers several
  warncells, one row each; `weather_observations` (place, metric, value nullable,
  unit, observed_at, station_ref) UNIQUE `(place, metric, observed_at)`. Both are
  DWD-state snapshots — **no FK into BBZ records**, everything re-fetchable. All
  `timestamptz` (ADR-0017). The refresh singleton (E18-06) upserts on those keys.
  Real `alembic up/down/up` verified. `test_weather_schema.py`.
- **#385 (E18-06) weather refresh singleton + health** — new `weather-refresh`
  cluster singleton (4th, ADR-0018) ticks `WeatherRefreshService.refresh()`:
  polls the active weather integration (`active_weather_provider()`, setting
  `weather_integration_id` = `dwd`) for each advertised capability, upserts
  normalized warnings → `weather_alerts` (a full fetch is authoritative — drops
  what DWD stopped publishing) and observations → `weather_observations`, puts the
  radar frame series in the per-node `RADAR_CACHE` (E18-03), and records per-kind
  outcome in `weather_refresh_state` (migration `0039`). **Never raises** — a fetch/parse
  failure is logged + recorded, last-good data stays. `health()` →
  `ok` / `stale` (last success older than `weather_stale_after_seconds`) /
  `degraded` (last attempt failed after a success) / `down` (never succeeded);
  overall = worst kind. The adapters (E18-02/04) own producing the normalized
  item contract from CAP XML / POI CSV; against the shipped `dwd` stub every kind
  is `down`. `test_weather_refresh.py`. `test_cluster_workers.py` gains the 4th
  singleton.
- **#387 (E18-07) weather read API** — `bbz_core.api.v1.weather` +
  `WeatherReadService`. `GET /api/v1/weather/{alerts,observations,radar,regions}`,
  all `weather.view`. `alerts` (optional `?region=`), `observations` (latest per
  place+metric, optional `?place=`), `radar` (frame series from the per-node
  `RADAR_CACHE` the E18-03 refresh fills; optional `?area=`, default
  `weather_radar_area`), `regions` (distinct regions/places we hold data for).
  Every response carries `attribution`
  ("Deutscher Wetterdienst", ADR-0026) + the `health` block from
  `WeatherRefreshService.health()` (overall + per-kind status / last_success /
  age). UTC times. `test_weather_api.py`.
- **#389 (E18-08) create BBZ event from a warning** — `POST /api/v1/weather/
  alerts/{alert_id}/create-event` (`weather.create_event`, idempotent on
  `X-Command-Id`). `WeatherEventService.create_from_alert`: loads the alert,
  builds an event (`source = "weather"`, title from the headline, description =
  DWD text + the operator's "— Bewertung —" block), `EventRepository.add` emits
  `EVENT_CREATED`, links it via the new `weather_alert_events` table (migration
  `0040`; `event_id` UNIQUE, `weather_alert_id` SET NULL so the link + its
  `source_ref` survive a refresh dropping the alert), and audits
  `WEATHER_EVENT_CREATED` (critical) with `weather_alert_id` / `source_ref` /
  `region` / `priority`. **Never automatic** — there is no operator-less path
  (§10). `test_weather_create_event_api.py`.
- **#377 (E18-02) DWD warnings adapter — LIVE** — `integrations/dwd/warnings.py`:
  `parse_cap_alerts` (pure) turns each `(alert, de-DE info, area)` of a CAP 1.2
  XML into a normalized dict — `region`=areaDesc, `type`=event, `level` 1–4 from
  `severity`, `valid_from`=onset, `valid_to`=expires (often absent), headline,
  description+instruction, `source_ref`=identifier, `warncell_id`;
  `msgType=Cancel` and geocode-less areas drop out. `DwdWarningsClient` fetches
  the lexically-last `…_DISTRICT_DE.zip`, unzips, parses, filters to warncells —
  stdlib `urllib`/`zipfile`/`ElementTree`, **no new dependency**, blocking work in
  `asyncio.to_thread`. `DwdWeatherProvider.get_warnings` resolves the configured
  place names → DISTRICT warncells via the vendored
  `data/mittelfranken.json`, and returns the `as_item()` dicts E18-06 stores.
  **ADR-0026 amended**: feed COMMUNEUNION → DISTRICT (Gemeinde level was far too
  fine). Fixtures are **real** DWD alerts (`tests/fixtures/cap_district/real_*.xml`,
  polygons stripped) + synthetic ones for the filter / cancel paths; CI never
  touches the network (`test_cluster_workers` weather tick pointed at nothing).
  `test_dwd_warnings.py` + an end-to-end `test_weather_refresh.py` case: real
  provider (stubbed transport) → refresh → `weather_alerts` row → health.
- **#381 (E18-04) DWD observations adapter — LIVE** — `integrations/dwd/observations.py`:
  `parse_poi_csv` reads the DWD POI `<station>-BEOB.csv` (3 header rows,
  semicolon, latin-1, decimal comma, `---` = missing) and normalises the newest
  row's temperature / humidity / wind_speed / wind_gust / precipitation /
  pressure / cloud_cover to the E18-06 observation contract (UTC `observed_at`
  from `Datum` + `Uhrzeit (UTC)`). `DwdWeatherProvider.get_observations` fetches
  one CSV per configured place that has a `poi_station_id`
  (`data/mittelfranken.json`: Nürnberg/Fürth/Erlangen/Schwabach → 10763,
  Ansbach / Neustadt a.d. Aisch → none → "keine Daten"); a single failing station
  is skipped, all-fail raises `DwdObservationsError`. Fixtures are **real**
  trimmed POI CSVs. `test_dwd_observations.py`; the `test_weather_refresh.py` E2E
  now drives warnings **and** observations end to end.
- **#379 (E18-03) DWD radar adapter — LIVE** — `integrations/dwd/radar.py`:
  `parse_time_dimension` reads the ISO8601 `time` dimension
  (`<start>/<end>/PT5M`) of the GeoServer WMS layer `Radar_rv_product_1x1km_ger`
  (RV composite, analysis + nowcast) from a stdlib-`ElementTree` GetCapabilities
  parse; `build_frames` turns `(latest, step)` into the last `frame_count`
  (default 12) **GetMap URLs**, oldest → newest, clipped to the Mittelfranken
  bbox (`crs=CRS:84`, `image/png`, transparent). The images are **not** proxied —
  a frame is a ready URL the browser fetches from DWD directly (per-node
  `RADAR_CACHE` holds only `{frame_time, image_ref}`). `DwdRadarClient.frames()`
  takes layer / bbox / size per call so config always wins; the blocking
  GetCapabilities read runs in `asyncio.to_thread`. `WeatherRefreshService.
  _store_radar` parses the items into `RADAR_CACHE[weather_radar_area]` (new
  setting `weather_radar_area` = `mittelfranken`, also the E18-07 `/radar`
  default), sorted, bounded to `frame_count`; a WMS outage raises `DwdRadarError`
  → the refresh keeps the last frames + health `degraded`. `DwdNotImplementedError`
  removed — the adapter is fully live. Fixture is a trimmed real GetCapabilities
  (`tests/fixtures/wms/getcapabilities_radar.xml`). `test_dwd_radar.py`; the
  `test_weather_refresh.py` E2E now drives warnings **+** observations **+** the
  12-frame radar series end to end.
- **#393 (E18-10) recorded-fixture suite + degraded/recovery paths** —
  `integrations/dwd/tests/fixtures/README.md` documents every fixture's provenance
  (real vs synthetic, what was trimmed). New `test_dwd_degraded.py` (corrupt zip,
  truncated CAP member, non-de-only alert, all-`---` POI row, unparseable
  timestamp, thin CSV, GetCapabilities without a `time` dimension / without our
  layer → each raises the typed error or returns a thin-but-valid list) and
  `test_dwd_no_network.py` (autouse fixture makes `urllib.request.urlopen` raise;
  every adapter still parses its fixture end to end). `test_weather_refresh.py`
  gains degradation→recovery (`degraded`/`stale` → next good refresh → `ok`,
  `last_error` cleared), `overall` = worst kind, and "a failed radar refresh
  keeps the cached frames". `.ai/TESTING.md` gets a DWD section. **PR CI touches
  no network.** `dwd` test count 43.
- Only **E18-09** (Wetterlage UI) left → Epic 07 (frontend, blocked).

### Epic 19 – Weytec Monitor Routing: **backend complete (9/10; E19-08 dialog UI → Epic 07)**
- **#395 (E19-01) DB schema** — migration `0041_monitor_schema` +
  `bbz_core.infra.models.monitor`. Four tables (MASTER_PROMPT §9): `monitor_inputs`
  (`key` unique — BBZ-OS / BKU1-4 / Cayuga 1-2), `monitor_outputs` (`key` unique,
  `grid_row`/`grid_col` for the six workplace monitors, `is_large_display` for the
  Mittelmonitor/Großbild; CHECK `monitor_outputs_grid` = a workplace monitor sits
  at row 0-1 × col 0-2, a large display has no slot; UNIQUE `(grid_row, grid_col)`),
  `monitor_routes` (`output_id` **PK** → exactly one active input per output;
  `input_id` FK RESTRICT, `set_by` FK users SET NULL, `set_at`, `profile_id` FK
  SET NULL), `monitor_profiles` (`scope` CHECK `user`/`workplace`, exactly one of
  `owner_user_id` / `workplace_id` set — CHECK `monitor_profiles_scope_owner` —,
  `layout` JSONB). **Schema only** — the fixed input/output catalog + the standard
  layout are the E19-02 seed; the "lower-left is always BBZ-OS" rule is E19-03.
  `workplace_id` is a plain UUID (no `workplaces` entity yet). Real
  `alembic up/down/up` + `alembic check` (no drift) verified. `test_monitor_schema.py`.
- **#397 (E19-02) domain model + standard layout** — pure
  `bbz_core.domain.monitor`: `catalog.py` (the fixed §9 hardware layout —
  `INPUTS` bbz-os/bku1-4/**coda1-2** [MASTER_PROMPT writes "Cayuga"; canonical
  name is Coda, see glossary], `OUTPUTS` workplace1-6 at their 3x2 slots +
  large-display, `BOTTOM_LEFT_OUTPUT_KEY` = `workplace4`, `STANDARD_LAYOUT`
  output→input map with `workplace4 → bbz-os` per §9); `layout.py`
  (`validate_assignment` / `validate_layout` → `MonitorDomainError` for unknown
  keys or an incomplete/over-full map; `standard_layout()` returns a copy).
  Migration `0042_monitor_catalog_seed` inserts the 7+7 catalog + the standard
  layout into `monitor_routes` (idempotent `ON CONFLICT DO NOTHING`; downgrade
  removes only the seeded rows). Real `alembic up/down/up` + `alembic check`
  (no drift) verified; the seeded bottom-left route resolves to `bbz-os`.
  `test_monitor_domain.py` (10, pure unit).
- **#398 (E19-03) fixed rule: lower-left is always BBZ-OS** — enforced in the
  domain (`bbz_core.domain.monitor.layout`), so every write path is subject to it:
  `FIXED_ASSIGNMENTS = {workplace4: "bbz-os"}`, `validate_assignment` raises
  `FixedRouteViolation` (a `MonitorDomainError`) for any other input on a fixed
  output, `validate_layout` inherits it, `is_fixed_output` / `fixed_input_for`
  for the UI (E19-08). Pure — `test_monitor_domain.py` (14). The "via API direkt"
  rejection is re-verified at the HTTP layer in E19-04.
- **#404 (E19-06) `monitor_mock` — complete provider** (done ahead of E19-04,
  which depends on it). `integrations/monitor_mock/adapter.py` `MockMonitorProvider`
  implements the SDK `MonitorProvider`: `list_inputs`/`list_outputs`/`get_routes`,
  `set_route(*, output_id, input_id, command_id)`, `apply_layout(*, layout,
  command_id)`. Deterministic (in-memory map, read straight back);
  **`command_id`-idempotent** (a repeat replays the first result, never
  re-applies); `apply_layout` is atomic; config `unreachable_outputs` simulates a
  dead sink (`OutputUnreachableError`, health `degraded`); unknown port →
  `UnknownPortError`. Ports default to the E19-02 catalog keys so E19-10 routes
  them unchanged. **BBZ policy (the lower-left rule) is NOT in the mock** — it is
  enforced upstream (E19-03 domain). `manifest.json` → v1.0.0.
  `test_mock_monitor.py` (11).
- **#400 (E19-04) routing API + `MONITOR_ROUTE_CHANGED`** —
  `bbz_core.infra.repositories.monitor_routing.MonitorRoutingService` +
  `bbz_core.api.v1.monitor`. `GET /api/v1/monitor/routes` (`monitor.view`) →
  input/output catalog + current route per output + `is_fixed` flag + provider
  health. `PUT /api/v1/monitor/routes` (`monitor.route`, batch
  `{assignments: {output_key: input_key}}`) and `POST
  /api/v1/monitor/routes/reset-standard` (`monitor.reset_standard`) — both
  idempotent on `X-Command-Id` (`idempotent()` — a replay applies nothing). The
  service validates via the domain (unknown key / fixed rule → 422), calls
  `active_monitor_provider().set_route(... command_id=…)` per **changed** output
  (the provider is itself command-idempotent, E19-06), upserts `monitor_routes`
  and writes one `MONITOR_ROUTE_CHANGED` audit row (before/after input) per
  change — all in one tx. `MONITOR_ROUTE_CHANGED` added to `AuditAction` +
  `CRITICAL_ACTIONS`. New setting `monitor_integration_id` = `monitor_mock`;
  `active_monitor_provider()` in `integrations_host`. No provider → 503; provider
  reject → 503. `test_monitor_routing_api.py` (8, against `monitor_mock`).
  **NB** external provider execution via the outbox is deferred to E19-07.
- **#402 (E19-05) layout profiles** —
  `bbz_core.infra.repositories.monitor_profiles.MonitorProfileService` + profile
  routes on `bbz_core.api.v1.monitor`. `GET /monitor/profiles?workplace_id=` +
  `POST` / `PUT /{id}` / `DELETE /{id}` (`monitor.manage_profiles`) +
  `POST /{id}/apply` (`monitor.route`, idempotent). A profile is a named full
  `{output_key: input_key}` layout, `validate_layout`-checked on create/update
  (incl. the fixed rule). Scope `user` (private to `owner_user_id`) or
  `workplace` (visible with a matching `?workplace_id`; `workplace_id` is a plain
  UUID). Name unique per scope — migration `0043_monitor_profile_name_uq` (two
  partial unique indexes) + a service pre-check → 409. **Apply** goes through
  `MonitorRoutingService.apply_assignments` (shared with direct routing — same
  fixed-rule enforcement + `MONITOR_ROUTE_CHANGED` per change, route rows stamped
  with `profile_id`) and then writes one `MONITOR_PROFILE_APPLIED` audit
  (`AuditAction` + `CRITICAL_ACTIONS`). `test_monitor_profiles_api.py` (9).
- **#406 (E19-07) `monitor_weytec` scaffold** — `integrations/monitor_weytec/`:
  `WeytecMonitorProvider` is protocol-shaped
  (`bbz_integration_sdk.providers.MonitorProvider`) with an honest lifecycle
  (`HealthState.DISABLED`, empty `capabilities()`); **every routing call raises
  `WeytecNotConfiguredError`** (a `NotImplementedError`). `manifest.json`
  `capabilities: []` + `pending_vendor_documentation: [...]`, `mock: false`.
  `docs/integrations/weytec-monitor-pending.md` is the blocker (Do-NOT-invent
  table + unblocking checklist), referenced from `README.md` + "Open external
  dependencies". The Weytec API is **not invented** (MASTER_PROMPT §9, RULES.md);
  `monitor_mock` (E19-06) is used for dev + all tests. `test_weytec_scaffold.py`
  (7).
- **#410 (E19-09) permissions seed guard** — the four `monitor.*` keys are
  already seeded by the generic 0008 migration (it iterates `CATALOG` /
  `BUILTIN_ROLES` at run time), so like E10-14 this is a **policy-lock test** +
  doc, no new migration. `test_monitor_permissions_seed.py` (11): all four keys
  in `CATALOG["monitor"]`; `monitor.reset_standard` / `monitor.manage_profiles`
  are Administrator/Sichtleiter only; Disponent = `view` + `route`; Nur Lesen ≤
  `monitor.view`; Nachbearbeitung none; no role grants an unknown `monitor.*`
  key; and a DB-backed check that `seed_rbac` actually wrote those grants.
  `docs/domain/permission-catalog.md` gets the default-grants table.
- **#412 (E19-10) routing E2E** — `server/tests/test_e2e_monitor_routing.py`
  walks all four scenarios as one operator session against `monitor_mock`:
  set a route → the mock reflects it + `MONITOR_ROUTE_CHANGED`; the lower-left
  reassignment → 422, nothing changes; save a layout profile + apply it → routes
  match, `workplace4` stays `bbz-os`, `MONITOR_PROFILE_APPLIED`; reset-standard →
  the documented default. The browser half is scaffolded
  (`apps/web/e2e/monitor-routing.spec.ts`, `test.fixme`) pending the E19-08
  dialog. `.ai/TESTING.md` + `docs/mockup-parity-checklist.md` (rows 44–46 →
  `backend-done`) updated.
- **Only E19-08** (dialog UI — 3×2 grid, drag & drop **and** keyboard/select
  alternative, standard-layout button, profile save/load, locked lower-left) is
  left → Epic 07 (frontend, blocked).

### Epic 21 – Enterprise Authentication: **in progress (7/8)**
- **#431 (E21-01) Entra ID / OIDC provider** — `bbz_core.auth.oidc` (pure,
  framework-free): `pkce` (S256 only), `discovery` (fetch metadata, assert the
  issuer matches), `flow.start` (authorization-code URL with state / nonce /
  `code_challenge`; `response_type=code`, never implicit) + `flow.exchange`
  (token endpoint, `code_verifier`), `idtoken.validate_id_token` (JWKS `kid`
  match, **RS/ES/PS only — `none` and HMAC rejected**, `iss`/`aud`/`exp`/`iat`
  via PyJWT, then constant-time `nonce` compare), `http` (stdlib `urllib` in a
  thread — no new runtime dep; HTTPS-only). `OidcLoginService`
  (`infra/repositories/oidc_login.py`) holds the per-attempt secrets in
  `oidc_login_flows` (migration `0044`; `state` PK, Fernet-encrypted
  `code_verifier` derived from `jwt_secret`, TTL `oidc_login_flow_ttl_seconds`),
  **single-use** (the row is deleted at the top of `complete()` — a replay finds
  nothing), and audits `LOGIN_SUCCEEDED` / `LOGIN_FAILED` (provider + reason).
  DB-backed so a post-failover callback on another node resolves. API:
  `GET /api/v1/auth/oidc/{provider}/start` → `{authorization_url}`,
  `POST /api/v1/auth/oidc/{provider}/callback` `{code, state}` → the same session
  cookies as `/login` (session-minting refactored into `_issue_session`). JIT
  provisioning is `oidc_jit_provisioning` (off by default — an unknown `sub` →
  401; **policy is E21-02**). Settings `oidc_entra_{issuer,client_id,
  client_secret,redirect_uri}` — real values are an open external dependency;
  tests use a **mock IdP** (RSA keypair + canned discovery/JWKS/token, no running
  server). `test_oidc_login.py` (19): PKCE, the auth URL, id-token validation
  happy + bad-nonce / wrong-aud / wrong-iss / expired / `alg=none` / foreign-key
  forgery, replayed & unknown & expired `state`, unprovisioned principal,
  cross-node state, and **local password login still works**. Local logins are
  unaffected (`local` stays the registry default).
- **#433 (E21-02) OIDC group→role mapping + JIT policy** — `auth_group_mappings`
  (admin config: "provider group X grants role Y"; migration `0045`) +
  `external_role_assignments` (provenance — which `user_roles` rows the mapping
  owns). `GroupMappingService.sync_user_roles` runs on **every** external login
  (from `OidcLoginService._finish`): recomputes the mapped roles from the
  `groups` claim, adds new ones, drops ones whose group is gone — **never
  touching a manually-assigned role** (no provenance row) — auditing
  `USER_ROLE_ASSIGNED` / `USER_ROLE_REVOKED` per change; a login with an
  unchanged group set writes nothing. Admin API `GET/POST/DELETE
  /api/v1/auth/group-mappings` (`roles.manage`, `AUTH_MAPPING_CHANGED` audit — a
  critical action; duplicate rule → 409, unknown role → 422). JIT: setting
  `oidc_jit_default_role` (empty ⇒ a JIT user has only its mapped roles — the
  AC). `test_oidc_group_mapping.py` (7): reconcile add/remove, manual grant
  untouched, no-op idempotency, group-claim-drives-roles across two logins,
  JIT-user-gets-only-mapped, CRUD gated + audited.
- **#435 (E21-03) LDAP / Active Directory bind login** — `bbz_core.auth.ldap`: a
  blocking `ldap3` client (new runtime deps `ldap3` 2.9.1 + `pyasn1>=0.6.4` for
  its CVE fixes; ldap3's deprecated `tagMap`/`typeMap` import is filtered in the
  pytest config).
  Service-account bind → user search → **user bind (the authentication)** →
  optional group search. **Encrypted transport enforced** — `ldaps://` or
  `ldap://` + StartTLS-before-bind; a plaintext URL with StartTLS off is refused
  (`LdapInsecureError`). Two or more comma-separated URLs form an
  `ldap3.ServerPool` (failover, per node). `LdapLoginService`
  (`infra/repositories/ldap_login.py`) runs the client in a worker thread
  (`asyncio.to_thread`), resolves the principal to a BBZ user, reconciles roles
  through the **shared** `GroupMappingService` (E21-02), and audits
  `LOGIN_SUCCEEDED` / `LOGIN_FAILED` (`provider=ldap_ad`). `/api/v1/auth/login`
  tries local auth first and only falls back to a directory bind on a
  `BAD_CREDENTIALS` result with `ldap_ad` in `BBZ_AUTH_PROVIDERS` — one generic
  `invalid credentials` on failure; `LOCKED` locals never reach LDAP; a directory
  outage degrades to **local logins only**. JIT off by default
  (`ldap_jit_provisioning`). Settings `ldap_{url, bind_dn, bind_password,
  user_search_base, user_filter, group_search_base, group_filter, uid_attr,
  name_attr, mail_attr, start_tls, tls_verify, tls_ca_file}` — the bind password
  is a secret; the real connection values are an open external dependency
  (checklist in `docs/auth/ldap-directory.md`). No schema change (no migration).
  `test_ldap_login.py` (12): bind + groups, wrong / unknown creds, plaintext
  refused, StartTLS-before-bind, provisioned + JIT + reconcile, failure audited,
  `/login` fallback happy + bad-password, **local login unaffected** — all
  against a containerised OpenLDAP (skipped when unreachable).
- **#437 (E21-04) directory sync job** — `directory-sync`, a leader-elected
  singleton (added to `workers/registry.py`) that reconciles BBZ against the
  directory once per `ldap_sync_interval_seconds`. `LdapClient.enumerate_principals`
  paged-searches every account (`ldap_user_list_filter`) with its groups;
  `DirectorySyncService` (`infra/repositories/directory_sync.py`) diffs against the
  `ldap_ad` identities: **new** → provision (if `ldap_sync_provision`), **gone**
  → **soft-deactivate** (`status=disabled` + revoke sessions, never a hard delete)
  auditing `USER_DEACTIVATED`, **present** → refresh display name + reconcile
  group-mapped roles via the shared `GroupMappingService` (E21-02). Safety: a run
  that returns **zero** accounts, or would deactivate more than
  `ldap_sync_max_deactivations` (default 20), aborts and changes nothing — a
  directory outage must not mass-off-board. Admin API `POST /api/v1/auth/directory-sync`
  `{dry_run, force}` + `GET …/state` (`users.manage`); **dry run writes nothing**
  (computes the diff, returns it). Every real run audits
  `DIRECTORY_SYNC_COMPLETED` (both critical actions) and upserts
  `directory_sync_state` (migration `0046`; PK `source`). The manual admin
  `POST /users/{id}/deactivate` now also audits `USER_DEACTIVATED` (closed a
  stale TODO). Entra sync (MS Graph) is a separate future item — Entra users
  arrive via OIDC JIT today. `test_directory_sync.py` (20): provision / disable /
  JIT role, soft-deactivate + session revoke + audit + row kept, the cap aborts,
  `force` overrides, empty result aborts, LDAP error recorded not raised, group
  reconcile add+remove, display-name refresh, local user untouched, dry-run
  writes nothing, completion audit + state row, the tick honours the interval,
  and two real-OpenLDAP end-to-end tests + the gated admin API.
- **#439 (E21-05) MFA policy engine + step-up** — `mfa_policies` (migration
  `0047`; PK `role_key`, `grace_period_days`) makes MFA a **role-based**
  requirement: a user requires MFA iff they hold any policy'd role (direct or via
  a group). `MfaPolicyService.evaluate(user_id)` → `MfaRequirement(required,
  in_grace, grace_until)`; grace deadline = earliest `grant_time + grace_days`
  across the user's policy'd roles. **Login enforcement** (`_enforce_mfa_policy`,
  shared by local / OIDC-callback / LDAP-fallback): no factor + grace elapsed →
  `401 mfa_required` + `LOGIN_FAILED`; still in grace → login succeeds with
  `mfa_enrolment_required: true` + `mfa_grace_until` on the response (the client
  nudges enrolment). A user who also enrolled a **local** TOTP satisfies the
  requirement on any provider. External logins can be exempted with
  `mfa_policy_enforce_external=false`. **Step-up**: `require_stepup(perm)`
  (composes `require`) demands a *fresh* MFA verification for permissions in
  `mfa_stepup_permissions` (default `["permissions.manage"]`) — `sessions.mfa_verified_at`
  (new column) is stamped by a TOTP login and by `POST /api/v1/auth/mfa-policies/step-up`
  `{totp}`, and must be within `mfa_stepup_max_age_seconds` (default 300); a
  stale session gets `401 step_up_required` + `MFA_STEPUP_REQUIRED` audit. Wired
  onto `PUT /roles/{id}/permissions` (RBAC) and the MFA-policy writes. Admin API
  `GET/PUT/DELETE /api/v1/auth/mfa-policies[/{role_key}]` (`permissions.manage`,
  `MFA_POLICY_CHANGED` audit; both new actions are critical). Session store
  threaded `mfa_verified` through `SessionStore.create` +
  `SessionStore.mark_mfa_verified`. `test_mfa_policy.py` (15): evaluate
  direct/group/grace, `blocks()` logic, the external toggle, login blocked / in
  grace / normal-with-TOTP, `mfa_verified_at` stamping, step-up block→step-up→
  unblock, TOTP-login-counts-as-step-up, step-up expiry, admin CRUD gated +
  audited. **Not built**: scope-based (only role-based) policies; Entra/OIDC
  external factor verification (WebAuthn is E21-06).
- **#441 (E21-06) WebAuthn / FIDO2** — a phishing-resistant second factor for
  local accounts. New dep `webauthn` (py_webauthn 3.x; pulls `cbor2`,
  `pyasn1-modules`, `pyOpenSSL` — all pip-audit clean). `webauthn_credentials`
  (per local `auth_identity`) + `webauthn_challenges` (DB-backed single-use
  server challenge for HA; migration `0048`). `WebauthnService`
  (`infra/repositories/webauthn.py`) wraps the ceremonies:
  `begin/complete_registration`, `begin/verify_authentication`, `list/remove`,
  `has_active`. Self-service API `POST/GET/DELETE /api/v1/auth/webauthn/...`
  (`register/options`, `register/verify`, `credentials`, `credentials/{id}`,
  `authenticate/options`). **Login**: `webauthn` field on `LoginRequest`; a user
  with a credential and no assertion gets `401 webauthn_required` with the
  request options in `error.details.options`, then retries. `_mfa_satisfied`
  (E21-05) now also counts a WebAuthn credential, and `POST …/mfa-policies/step-up`
  accepts `{webauthn}`. `_issue_session` takes a bare `user_id` now (a challenge
  write mid-login expires ORM objects — the login handlers capture user fields
  into locals). Settings `webauthn_{rp_id, rp_name, origins, require_user_verification,
  challenge_ttl_seconds}` — empty `rp_id` ⇒ 503 (a real RP id/origin is a
  deployment input). Audit `WEBAUTHN_REGISTERED` / `WEBAUTHN_REMOVED` (not
  critical, matching TOTP `MFA_ENROLLED`). **Not built**: passwordless
  first-factor; challenging a WebAuthn factor on the OIDC/LDAP callback (those
  still use `has_active`); the CDP browser e2e → Epic 07. `test_webauthn.py`
  (11) drives an in-process P-256 software authenticator (hand-built
  attestation / assertion): register + list + isolation, login challenge +
  verify + bad-assertion + sign-count + single-use, passkey-satisfies-policy,
  step-up via assertion, removal, disabled-when-unconfigured.
- **#443 (E21-07) advanced RBAC — conditions, time-bound grants, delegation**
  (ADR-0027). **Conditions** (`role_permissions.condition`, since E02-07) now
  evaluate: `bbz_rule_dsl.RBAC_CONTEXT` (clock-only — `now.hour` / `now.weekday`
  / `now.iso` + the grant's `scope`), built per check in
  `resolver.condition_allows(grant, now=...)`, used by **both** `authorize()`
  and `authorize_scoped()`. Still gated by `rbac_conditions_enabled` (default
  **off** — opt-in); flag off / parse error / eval raise ⇒ deny. The condition
  JSON is validated (`RBAC_CONTEXT.validate`) at write time in
  `set_role_permissions` → 422 on a bad expression. **Time-bound grants**:
  `user_roles.valid_from` / `valid_to` (migration `0049`) — the grant store only
  returns grants inside the window, so an expired grant is simply not effective;
  `POST /users/{id}/roles` takes the optional window, `valid_to <= valid_from`
  → 422. **Delegation**: `permission_delegations` (always `expires_at`,
  revocable) — `DelegationService.delegate` (the delegator must currently hold
  the permission, else `NotDelegatorsToGive`; `PERMISSION_DELEGATED` audit) /
  `revoke` (`PERMISSION_DELEGATION_REVOKED`); the grant store folds active
  delegations into the delegatee's effective permissions, so a revoke / expiry
  is effective on their next request. API `POST/GET/DELETE
  /api/v1/permissions/delegations` (`permissions.manage`). Both delegation
  actions are critical. `test_advanced_rbac.py` (13) + `RBAC_CONTEXT` DSL tests.
  **Not built**: approval workflows for delegations; request-derived condition
  fields (client/workplace).
- Next: E21-08 (account linking + auth-provider admin UI) — partly frontend.

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

## Architecture ADRs — status (after E01-01 / #20, 2026-08-29; E09-01, 2026-08-30)
**Accepted:** 0001, 0002 (baseline), 0003, 0004, 0005, 0006, 0007 monorepo
layout, 0008 backend stack & boundaries, **0009 agent language (Go) — E09-01**,
0010 rule DSL, 0011 event log + outbox/inbox, 0012 API/idempotency conventions,
0013 frontend stack & a11y, 0014 CI/CD & supply chain, 0015 config & secrets,
0016 Cayuga→Coda consolidation, 0017 time handling (UTC), 0018 distributed config
store (etcd).

**Still Proposed / decision pending:** none in the 0001–0018 range.

**Open points recorded on accepted ADRs:**
- ADR-0013: the coordinated `apps/web` major upgrade (PrimeVue 5 / Pinia 4 /
  vue-router 5 / Vite 8) is evaluated in issue #14; baseline stays PrimeVue 4.
- ADR-0015: the concrete runtime secret-store product → dedicated **ADR-0019**
  (E01-03 / #22), required before staging.

**New ADRs scheduled by the roadmap:** 0019 secret store (E01-03 / #22), 0020
audit immutability (E04-10 / #66, Proposed), **0021 PostgreSQL replication mode
(E06-02 / #82 — Accepted: synchronous + auto fallback)**, 0022 Electron load
strategy (E08-07 / #143), 0023 SIP gateway (E13-02 / #271).

**Added outside the roadmap schedule:** **0024 trigger execution via a
leader-elected drain worker (E15-15 / #333 — Accepted)** — a normalized inbound
signal is queued in the provider inbox and drained by the new `trigger-engine`
singleton; ingestion stays fast and cannot be broken by a rule.
**0025 door-open DTMF flow (E17-05 / #369 — Accepted)** — BBZ's
`door_action_profiles` is "the config store" the `send_dtmf` protocol note meant;
the DTMF **sequence** (not a BBZ id) crosses the provider boundary because an
integration can't resolve a BBZ id. SDK `send_dtmf(dtmf_profile_id=…)` renamed to
`send_dtmf(dtmf=…)`. `DoorOpenService` decrypts transiently, drives the provider
through a `door_open_commands` state machine, audits without the code.
**0026 DWD Open Data endpoints (E18-01 / #375 — Accepted)** — the `dwd`
integration uses CAP 1.2 warnings (`opendata.dwd.de/weather/alerts/cap/`), the
DWD GeoServer WMS for radar, and POI CSV for observations; poll + cache, degrade
to last-good on failure, region/place→id mapping vendored not runtime-fetched.
Rejected the undocumented `app-prod-ws.warnwetter.de` app backend.

## Open external dependencies
- exact Cisco CUCM version/SU and productive cluster/CTI configuration (§8.18)
- Weytec API documentation — `monitor_weytec` is an interface-only scaffold
  (E19-07); blocker + unblocking checklist in
  `docs/integrations/weytec-monitor-pending.md`
- Coda Video (HxGN dC3 Video) partner/API/SDK documentation for alarm ingress and
  camera/display control
- Siedle Access DTMF door-open profile (secret/config; operating concept)
- Entra ID OIDC connection parameters (issuer / client id / secret / redirect URI)
- LDAP / AD connection parameters — directory hosts, service-account DN + password,
  search bases, group filter, CA chain; client is built (E21-03), checklist in
  `docs/auth/ldap-directory.md`

CUCM/Coda/Weytec/Siedle integrations are built strictly from documented vendor
interfaces. No customer-specific or vendor API is invented.

## Open decisions / questions (carried from planning)
- commit the functional HTML mockup into the repo
- ~~confirm ADR-0009 (Go vs. Rust for agents)~~ → **Go** (ADR-0009 Accepted,
  E09-01); shared libs `discovery` / `outbox` / `commandenvelope`
- BKU workstation OS + corporate browser (launch mechanism)
- offline→online conflict-resolution policy
- Electron: load web build from server vs. bundle
- multi-BBZ / multi-tenancy scope (`region`/`bbz` scopes)
- LICENSE choice + container-registry mirror (see `docs/repo-settings.md`)
- ~~synchronous vs. asynchronous PostgreSQL replication mode~~ → **ADR-0021**
  (synchronous with automatic fallback)
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
