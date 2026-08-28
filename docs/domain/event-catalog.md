# Domain event catalog (seed)

Seeded from MASTER_PROMPT §3. This is the **starting list**; Phase 1 finalizes
payloads and `schema_version` policy (ADR-0011). Envelope schema:
`packages/event-schemas/.../domain_event.envelope.v1.json`.

## Events

| event_type | aggregate | notes |
|---|---|---|
| EVENT_CREATED | event | |
| EVENT_ACCEPTED | event | |
| EVENT_ACKNOWLEDGED | event | |
| EVENT_OPENED | event | |
| EVENT_ASSIGNED | event | ownership = whole event |
| EVENT_TAKEN_OVER | event | audited; only when owner is Pause/offline |
| EVENT_ARCHIVED | event | leaves the work queue, stays in history |
| EVENT_REACTIVATED | event | never one-click; explicit confirmation |
| ACTION_STEP_COMPLETED | workflow_instance | |

## Calls

| event_type | notes |
|---|---|
| CALL_RINGING / CALL_ANSWERED / CALL_ENDED | lifecycle |
| CALL_DOCUMENTED | mandatory category set (§13.10) |

## Contacts / monitor / weather

| event_type | notes |
|---|---|
| CONTACT_CREATED / CONTACT_PRIORITY_CHANGED | |
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
