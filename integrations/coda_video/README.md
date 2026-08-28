# coda_video (MOCK ONLY)

Canonical id for the video platform formerly planned as "Cayuga":
**Coda Video (HxGN dC3 Video)** — see ADR-0006 and `.ai/INTEGRATIONS_CODA_VIDEO.md`.

## What is here

A mock provider that simulates:

- video: `resolve_camera`, `open_camera`, `open_camera_group`
- alarm ingress: `subscribe_alarms`, `resolve_source`, `get_context` with a
  `simulate_alarm(...)` test helper for panic / intrusion / generic alarms

## What is deliberately NOT here

No real endpoints, auth, event payloads, alarm acknowledgement methods, camera
IDs, display-agent commands, SDK class names or licensing assumptions. The raw
payload shape accepted by `simulate_alarm` is the mock's own invention for
testing and makes **no claim** about the real Coda API.

The productive integration is implemented in a later phase, strictly from the
official Coda / HxGN dC3 Video API/SDK documentation (external dependency — see
`.ai/CURRENT_STATE.md`).

## HA / exactly-once

`normalize_alarm` always sets a stable `provider_event_id`. Deduplication, the
durable provider-event inbox and the idempotent trigger executions live in the
core (Phase 1) so a duplicated or replayed alarm never creates a second BBZ
event.
