# Weytec Monitor / KVM Routing — vendor-integration blocker

> **Status: BLOCKED on official vendor documentation.**
>
> The `monitor_weytec` integration ships an **interface-only scaffold**
> (`integrations/monitor_weytec/adapter.py` — every routing method raises
> `WeytecNotConfiguredError`; `manifest.json` → `"capabilities": []`,
> `"pending_vendor_documentation": [...]`). No real Weytec endpoint, credential,
> command, identifier or SDK class exists in this repository. The Weytec API
> **must not be invented** — not from guesswork, blog posts, screenshots,
> competitor docs or any other unofficial source.

Source of truth: MASTER_PROMPT §9 ("Weytec-API nicht erfinden. Nur Interface
vorbereiten, bis Dokumentation vorliegt"), `RULES.md`, `.ai/CURRENT_STATE.md`
("Open external dependencies" → "Weytec API documentation").

## Do NOT invent

Until official Weytec project / vendor documentation is supplied, the following
must not be written from guesswork, blog posts, screenshots, competitor docs or
any other unofficial source:

| # | Area | Why guessing is dangerous |
|---|------|---------------------------|
| 1 | **Endpoint URLs / base paths / transport** (REST, a control protocol, a local agent) | a wrong host or path fails silently, or drives an unintended device |
| 2 | **Authentication scheme** (token / mTLS / session / API-key / none-on-LAN) | a wrong assumption bakes broken or insecure auth into production config |
| 3 | **Routing commands** (set one output, apply a whole layout, atomicity, ack semantics) | a wrong call could switch the wrong monitor, or half-apply a layout in the control room |
| 4 | **The layout / video-wall model** (how the 3×2 + large display map to device outputs) | the core addresses outputs by the normalised catalog key (E19-02); a vendor object model leaking across the boundary breaks that contract |
| 5 | **Input / output identifiers** | the fixed "lower-left = BBZ-OS" rule (E19-03) is keyed on the normalised output; a mismatched device id defeats it |
| 6 | **Command idempotency / echo** | the routing service passes a `command_id` (E19-04); if the device does not dedupe, a retry double-switches |
| 7 | **SDK / library class names and signatures** | a real adapter imports the vendor SDK; invented names produce code that cannot build against it |
| 8 | **Licensing / edition** | `capabilities()` must reflect what is actually licensed, not what we hope |

## What IS implemented (vendor-neutral)

- **SDK contract** — `bbz_integration_sdk.providers.monitor.MonitorProvider`
  (`list_inputs` / `list_outputs` / `get_routes` /
  `set_route(*, output_id, input_id, command_id)` /
  `apply_layout(*, layout, command_id)`).
- **`monitor_mock`** (E19-06) — a complete, deterministic, `command_id`-idempotent
  in-memory router with failure simulation. Development and every test run
  against it.
- **Core runtime** — the domain catalog + standard layout + fixed-rule validation
  (E19-02/03), the routing API + `MONITOR_ROUTE_CHANGED` audit (E19-04), layout
  profiles + `MONITOR_PROFILE_APPLIED` (E19-05). All provider-agnostic — they
  drive whatever `monitor_integration_id` points at.
- **`monitor_weytec` scaffold** — this integration: discoverable, protocol-shaped,
  honestly labelled; every routing call raises.

## Unblocking checklist (when the documentation arrives)

1. Record the document source, version and access date in a new ADR.
2. Build a real adapter **only** from the supplied document; keep `monitor_mock`
   for tests.
3. In `integrations/monitor_weytec/manifest.json`: drop
   `"pending_vendor_documentation"`, set the real `capabilities`, move the base
   URL into `config_schema.json` and any credential reference into the secrets
   store (never the manifest).
4. Verify `capabilities()` against the actual licence / edition.
5. Map the device input/output identifiers to the E19-02 catalog keys in the
   adapter (the boundary), and re-run the E19-10 end-to-end against the real
   adapter in staging.

---
Referenced from `.ai/CURRENT_STATE.md` and `integrations/monitor_weytec/README.md`.
