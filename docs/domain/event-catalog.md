# Domain event catalog

Seeded from MASTER_PROMPT §3. Envelope schema:
`packages/event-schemas/.../domain_event.envelope.v1.json`. Per-`event_type`
payload schemas: `packages/event-schemas/.../event.payloads.v1.json` (one
sub-schema under `properties.<EVENT_TYPE>`).

## `schema_version` policy (ADR-0011, finalized E04-05)

* Every domain event carries an integer `schema_version` (envelope field), and
  every `event_type` in Phase 1 has a payload schema at that version.
* `append_event` **rejects** an event whose `event_type` has no registered
  payload schema (`UnknownEventTypeError`) or whose payload fails the schema.
* **Additive** changes (new optional field, wider enum) stay within the current
  major: edit `event.payloads.vN.json` in place.
* **Breaking** changes (rename/remove a field, narrow a type, new required
  field) ship a new `event.payloads.v(N+1).json`, bump the producer's
  `schema_version`, and add a migration note here. Old versions stay shipped so
  historical events keep validating on replay.
* **Payload data policy:** identifiers and enums only — never raw secrets,
  credentials, DTMF door codes or full call recordings in a payload.

## Events

| event_type | aggregate | payload (required) | notes |
|---|---|---|---|
| EVENT_CREATED | event | title, priority, actor_id | + description/bbz_id/workplace_id/source |
| EVENT_ACCEPTED | event | from, to, actor_id | |
| EVENT_ACKNOWLEDGED | event | from, to, actor_id | |
| EVENT_OPENED | event | from, to, actor_id | |
| EVENT_UPDATED | event | changes, actor_id | `changes` = `{field: {from, to}}` |
| EVENT_ASSIGNED | event | to_user_id, actor_id | + from_user_id; ownership = whole event |
| EVENT_TAKEN_OVER | event | from_user_id, to_user_id, actor_id | audited; only when owner is Pause/offline |
| EVENT_ARCHIVED | event | from, to, actor_id | + reason; leaves the work queue, stays in history |
| EVENT_REACTIVATED | event | from, to, actor_id, **reason** | never one-click; explicit confirmation |
| EVENT_NOTE_ADDED | event | note_id, kind, body, actor_id | kind ∈ {work, postprocess}; also audited (E20-04) |
| EVENT_NOTE_UPDATED | event | note_id, thread_id, version, kind, body, actor_id | note edit; new append-only version, old one kept; audited (E20-04) |
| ACTION_STEP_COMPLETED | workflow_instance | _(schema pending Epic 05)_ | |
| CALL_RINGING | call | bbz_call_id, direction, from, to | driven by a normalized provider event (E11-04); audited |
| CALL_ANSWERED | call | bbz_call_id, direction, from, to | first connect only; audited |
| CALL_ENDED | call | bbz_call_id, direction, from, to | call reached a terminal state; audited |
| LINE_IN_SERVICE | line | provider, external_id, state | line status change (E11-07); not audited |
| LINE_OUT_OF_SERVICE | line | provider, external_id, state | line outage (E11-07); not audited |
| CALL_DOCUMENTED | call | bbz_call_id, category, actor_id | mandatory call categorization set (E11-09); audited |
| CONTACT_PRIORITY_CHANGED | contact | contact_id, from, to, actor_id | `from` null on first assignment; `to` ∈ {low, medium, high}; same-level is a no-op (no event); audited (E14-03) |

## Calls

| event_type | notes |
|---|---|
| CALL_RINGING / CALL_ANSWERED / CALL_ENDED | lifecycle |
| CALL_DOCUMENTED | mandatory category set (§13.10) |

## Contacts / monitor / weather

| event_type | notes |
|---|---|
| CONTACT_PRIORITY_CHANGED | priority set/changed (§13.9); same-level = no-op; audited (E14-03) |
| CONTACT_CREATED | contact added (E14-05) |
| MONITOR_ROUTE_CHANGED | audited |
| WEATHER_EVENT_CREATED | event created from a DWD warning |

## Telephony (normalized, vendor-neutral)

See `packages/event-schemas/.../telephony_event.v1.json` — `CALL_OFFERED` …
`CTI_PROVIDER_OUT_OF_SERVICE`. Produced by the integration edge, never carrying
vendor types.

## Cross-cutting

| event_type | notes |
|---|---|
| TELEPHONY_RECONCILED | after CONTROL_LEADER change (ADR-0002) |
| Every critical action | writes an immutable `audit_events` row (§17) |
