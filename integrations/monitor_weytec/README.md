# monitor_weytec — Weytec Monitor / KVM Routing

**Interface-only scaffold (E19-07). BLOCKED on official Weytec documentation.**

The Weytec API is an open external dependency (`.ai/CURRENT_STATE.md` → "Open
external dependencies"). Per `RULES.md` / MASTER_PROMPT §9 it is **not invented**:
this integration is discoverable and its shape is pinned to the normalized
`bbz_integration_sdk.providers.MonitorProvider`, but every routing call raises
`WeytecNotConfiguredError`.

Full blocker + unblocking checklist:
[`docs/integrations/weytec-monitor-pending.md`](../../docs/integrations/weytec-monitor-pending.md).

For development and every test, use **`monitor_mock`** (E19-06) — a complete,
deterministic, `command_id`-idempotent in-memory router.

Logical model to satisfy (MASTER_PROMPT §9), owned by `bbz_core.domain.monitor`:

- inputs: BBZ-OS, BKU1–4, Coda 1–2
- outputs: 6 workplace monitors + large display, 3×2 layout
- fixed rule: the lower-left workplace monitor is always BBZ-OS (E19-03)
