# Coda Video / HxGN dC3 — vendor-integration blocker

> **Status: BLOCKED on official vendor documentation.**
>
> The `coda_video` integration ships a **mock adapter only**
> (`integrations/coda_video/adapter.py`, `manifest.json` → `"mock": true`). No
> real vendor endpoint, credential, payload shape, camera identifier or SDK class
> exists in this repository, and none may be added from guesswork.

Source of truth: [`.ai/INTEGRATIONS_CODA_VIDEO.md`](../../.ai/INTEGRATIONS_CODA_VIDEO.md),
**ADR-0006** ("implemented only from official project/vendor documentation"),
**ADR-0016** (`coda_video` is the canonical id; `Cayuga` is a legacy display
alias only). MASTER_PROMPT §31 / §36.

## Do NOT invent

Until the official Coda / HxGN dC3 Video project documentation is supplied, the
following must not be written from guesswork, blog posts, screenshots, competitor
docs, or any other unofficial source:

| # | Area | Why guessing is dangerous |
|---|------|---------------------------|
| 1 | **Endpoint URLs / base paths** | a wrong host or path fails silently, or reaches an unintended system |
| 2 | **Authentication scheme** (token / mTLS / session / API-key header / OAuth) | a wrong assumption bakes broken or insecure auth into production config |
| 3 | **Inbound event / alarm payload shapes** | the normaliser (E16-04) would map the wrong fields — a panic alarm could be silently dropped |
| 4 | **Alarm acknowledgement methods** | the BBZ event ack and the vendor ack are separate domain actions (E16-03); a wrong call could acknowledge or close the wrong thing |
| 5 | **Camera / object identifiers and the object model** | the core addresses cameras only by the normalised `camera_id` (E16-02); a vendor object id leaking across the boundary breaks that contract |
| 6 | **Display-agent / video-wall commands** | sending an invented command to an operator display is an uncontrolled side effect on the control room |
| 7 | **SDK / library class names and signatures** | a real adapter imports the vendor SDK; invented names produce code that cannot build against it |
| 8 | **Licensing / edition assumptions** | capability discovery (`capabilities()`) must reflect what is actually licensed, not what we hope is available |

## What IS implemented (mock, vendor-neutral)

- **SDK contracts** — `bbz_integration_sdk.providers.video` / `video_types`
  (typed `VideoProvider` + normalised result models, E16-02);
  `bbz_integration_sdk.providers.alarm_ingress` / `alarm_types` (typed
  `AlarmIngressProvider`; external ack is a separate opt-in protocol, E16-03).
  No vendor detail.
- **Mock adapter** — `integrations/coda_video/` `MockCodaVideoProvider`: a
  deterministic simulation of panic / intrusion / generic alarms, one or several
  cameras, unmapped sources, duplicates, reconnect-replay and camera failures
  (E16-09). Its raw payload shape is the mock's own invention for testing.
- **Core runtime** — alarm → immutable provider event + inbox dedupe (E16-04);
  trigger engine → exactly one critical event + published EPK version + popup
  (E16-07); camera open as a decoupled outbox side effect (E16-08); per-alarm-
  source admin config (E16-06); diagnostics API (E16-10); the §36.1 E2E (E16-11).

The manifest carries the machine-readable marker
`"pending_vendor_documentation": [...]` for as long as this blocker stands.

## Unblocking checklist (when the documentation arrives)

1. Record the document source, version and access date in a new ADR (extend the
   ADR-0006 notes).
2. Build a real adapter **only** from the supplied document; keep
   `MockCodaVideoProvider` for tests.
3. In `integrations/coda_video/manifest.json`: remove `"mock": true` and
   `"pending_vendor_documentation"`; move the real base URL into
   `config_schema.json` and the credential reference into the secrets store
   (never the manifest).
4. Verify `capabilities()` against the actual licence / edition.
5. Re-run the E16-11 §36.1 end-to-end against the real adapter in staging.

---
Referenced from `.ai/CURRENT_STATE.md` and `.ai/INTEGRATIONS_CODA_VIDEO.md`.
