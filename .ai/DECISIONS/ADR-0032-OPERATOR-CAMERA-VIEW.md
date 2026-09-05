# ADR-0032: Operator-facing per-event camera view

## Status
Accepted (2026-09-06, roadmap E16-12 / #357)

## Context

E16-12 (#357) asks for a **camera panel in the event detail / alarm-popup
context** that "displays / focuses the associated cameras" and shows a clear
"Video derzeit nicht verfügbar" on failure, without ever blocking event
editing. The issue is labelled `area:frontend` and assumes the read surface
exists. It does not:

- Camera opening is a **decoupled side effect** (ADR-0006, E16-08): alarm →
  trigger engine → `external_action_outbox` row → outbox dispatcher →
  `video.*` provider. The camera opens on a physical workplace / wall display;
  the provider exposes **no snapshot, thumbnail or stream** — only open / focus.
- On the **happy path nothing is recorded on the event.** Only a terminal
  failure appends a `CAMERA_ACTION_FAILED` domain event (with `camera_refs`,
  E16-08). So the event's own record cannot answer "which cameras belong to
  this event?".
- `Event` has no camera fields and no FK to the alarm-source `TechnicalEndpoint`
  (`Event.source` is the string `"trigger"` / `"weather"` / …).
- No operator-facing HTTP endpoint returns cameras for an event or their live
  status. `integrations.view` today gates only the admin integrations overview
  (`admin_integrations.py`); `/coda-alarm-sources` is admin-only; the `video.*`
  protocol is reachable only from workers.

`.ai/INTEGRATIONS_CODA_VIDEO.md` does envisage the operator seeing camera state
("associated camera references" as a normalised alarm field; "last successful
camera action"; open / focus associated cameras). A real camera panel — not
just a failure notice — is the intended end state, so this gets an ADR rather
than a silent re-scope (AGENTS.md).

## Decision

1. **Record the happy path.** When the outbox dispatcher successfully delivers
   an `open_camera` / `open_camera_group` row that carries an `event_id`, it
   appends a **`CAMERA_OPENED`** domain event to that event —
   `{action_type, camera_refs, workplace_id}`. Additive to
   `event.payloads.v1.json` (same shape family as `CAMERA_ACTION_FAILED`);
   best-effort, exactly like the existing failure note, and it never rolls back
   or blocks anything (ADR-0006 unchanged).

2. **One operator read endpoint.**
   `GET /api/v1/events/{event_id}/cameras` — permission **`integrations.view`**
   (as the issue specifies; its first operator consumer). Returns the union of
   camera refs seen in the event's `CAMERA_OPENED` / `CAMERA_ACTION_FAILED`
   domain events, each enriched via `video.resolve_camera`:
   `{provider_available, cameras: [{ref, name, site, online, group_ids,
   last_action, last_action_state}]}`. It **degrades** instead of failing:
   `NoActiveProvider` → `provider_available: false` and the refs with
   `online: null` (this is the "Video derzeit nicht verfügbar" case); a single
   `CameraNotFoundError` / timeout → that camera `online: null`, the rest still
   resolve. Read-only, not audited.

3. **One operator action endpoint.**
   `POST /api/v1/events/{event_id}/cameras/{camera_ref}/focus` — permission
   `integrations.view`, requires `X-Workplace-Id`, command-envelope idempotent,
   audited **`CAMERA_FOCUS_REQUESTED`** (critical). Enqueues one `open_camera`
   outbox row (the E16-08 handler) targeted at the **requesting operator's**
   workplace, carrying `event_id` so a delivery failure surfaces as
   `CAMERA_ACTION_FAILED` on the event. Same decoupled delivery + retry; a
   failure never blocks the operator.

Camera state never blocks event editing (AC of #357; ADR-0006).

## Consequences

- `event.payloads.v1.json` gains `CAMERA_OPENED`; archive / export bundles
  (E20-03 / E20-06) now include camera-open events — strictly more complete.
  `docs/domain/event-catalog.md` updated.
- `integrations.view` gains an operator consumer. The built-in `sichtleiter`
  and `administrator` roles already hold it; **`disponent` does not by
  default** — a deployment that wants the camera panel for front-line
  dispatchers grants `integrations.view` to that role (this also surfaces the
  read-only admin integrations overview to them). No built-in role is changed
  here.
- #357 becomes a genuine frontend task: `CameraPanel.vue` in
  `EventProcessingPanel`, consuming `GET /events/{id}/cameras`; a
  "Auf meinen Arbeitsplatz holen" button per camera → the focus endpoint;
  "Video derzeit nicht verfügbar" on `provider_available: false`; Playwright
  with the `coda_video` mock (camera on / off).
- Split delivery: one backend PR (this ADR — `CAMERA_OPENED` + the two
  endpoints + tests), then #357 as the frontend PR.

## Alternatives considered

- **Failure-notice only, no backend.** A panel that reads just the existing
  `CAMERA_ACTION_FAILED` events. Satisfies the literal AC but can never show
  "here are the cameras" — a degenerate panel. Rejected as under-delivery.
- **Re-derive from the alarm source at read time** (event → `trigger_executions`
  `result->>event_id` → `provider_event_id` → alarm signal →
  `associated_camera_ids`). No new domain event, but a fragile four-way join
  that only works for trigger-created events and misses the operator's own
  focus actions. Rejected in favour of recording `CAMERA_OPENED` explicitly.
- **A new dedicated `video.view` permission.** The issue names `integrations.view`
  and a camera panel is squarely an "integration view"; a fourth camera-only
  key is churn for no isolation benefit.
