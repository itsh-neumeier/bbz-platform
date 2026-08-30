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

### Epic 20 – Archive / Postprocessing: **in progress (2/8)**
- **#414 (E20-01) archive detail model** — decision documented in
  `docs/domain/archive.md`: **no `event_archive` table**; an archived event is an
  `events` row with `status=archived` and all history lives in the same
  append-only tables (ADR-0011). `ArchiveQueryRepository.detail(event_id)`
  (`bbz_core/infra/repositories/archive_queries.py`) bundles event detail +
  `domain_events` + workflow instances (task results, decisions, pinned template
  version) + audit refs + `calls` (reserved, Epic 11). Query only — the HTTP
  detail endpoint is E20-03 (#418). `test_archive_detail.py` proves
  active-vs-archived depth parity.
- **#416 (E20-02) archive list filters** — `GET /api/v1/events` gained optional
  `created_from`/`created_to`, repeatable `priority`, `bbz_id`, `assignee_id`
  (active responsible) filters; keyset cursor unchanged. `queue=active` still
  excludes archived and ignores the filters. `test_archive_list_api.py`.
**Next:** #418 (E20-03). Live issues: #418, #420, #422, #424, #426, #429.

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
audit immutability (E04-10 / #66, Proposed), **0021 PostgreSQL replication mode
(E06-02 / #82 — Accepted: synchronous + auto fallback)**, 0022 Electron load
strategy (E08-07 / #143), 0023 SIP gateway (E13-02 / #271).

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
