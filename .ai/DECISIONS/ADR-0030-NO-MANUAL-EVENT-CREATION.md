# ADR-0030: No manual event creation in the operator UI

## Status
Accepted (2026-09-03) — a scoped deviation from the V10 mockup, taken during the
Epic 07 mockup-alignment work (#98 / #716).

## Context

`docs/mockup/bbz-3sz-v10.html` (the binding UX reference, MASTER_PROMPT §13 /
`.ai/FEATURES.md`) has a **"+ Ereignis anlegen"** button on the Ereignisse view
that calls `createIncident()` and adds an event from a small form.

The backend supports this: `events.create` is a real permission and
`POST /api/v1/events` accepts `{title, priority, description}`.

But the product model is that events are **raised by documented triggers** — BMA
telephone triggers (§32), incoming calls that an operator escalates, Coda
panic/alarm ingestion (§16), DWD weather warnings (§10 / E18-08). Every event
therefore has a provenance and, where applicable, a bound workflow template
version. A free-form operator-created event has neither, and it invites the
"shadow ticketing system" failure mode the trigger rules exist to prevent.

MASTER_PROMPT §13.3 describes the Ereignisspeicher as a *shared work queue* and
its actions as *annehmen / quittieren / bearbeiten / archivieren* — consume, not
create. §13 never lists an operator "create event" action.

## Decision

**The operator web UI does not offer a manual "create event" control.** Events
enter the Ereignisspeicher only through:

- a technical trigger rule firing (`trigger-engine`, ADR-0024),
- `POST /weather/alerts/{id}/create-event` from a DWD warning (E18-08),
- Coda alarm ingestion (E16),
- future: an operator escalating an active call to an event (Epic 11 follow-up —
  this *is* trigger-shaped: it carries the call's provenance).

`events.create` stays a backend/automation permission. It is granted to the
service accounts that run the triggers, not to human operator roles by default.

The V10 "+ Ereignis anlegen" button is intentionally **not** ported.

## Consequences

- The Ereignisse view (#717) and the Arbeitsplatz Ereignisspeicher (#716) have
  no create affordance; the mockup-parity checklist notes this row as a
  deliberate deviation.
- If a real need for a manual, provenance-free event appears (e.g. a phone call
  with no matching trigger rule), the answer is an **"aus Anruf anlegen"** action
  in the comms sidebar that stamps the call as the source — a new ADR, not a
  bare form.
- No code to remove — the control was never built.

## Alternatives considered

- **Port the button as-is.** Rejected: no provenance, no workflow binding,
  undermines the trigger model.
- **Port it but gate it behind a rarely-granted permission.** Rejected: still
  produces provenance-free events; the permission would drift open over time.
