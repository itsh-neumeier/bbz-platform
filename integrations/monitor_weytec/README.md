# monitor_weytec (PLACEHOLDER — no code)

Weytec monitor/KVM routing provider. **Not implemented in Phase 0.**

Weytec API documentation is an open external dependency (`.ai/CURRENT_STATE.md`).
Per RULES.md the API is **not invented**. Only the normalized `MonitorProvider`
interface is prepared (in `bbz_integration_sdk`); this integration stays empty
until documentation is supplied and validated.

Logical model to satisfy (MASTER_PROMPT §9):

- inputs: BBZ-OS, BKU1–4, Coda 1–2
- outputs: 6 workplace monitors + large display, 3×2 layout
- fixed rule: lower-left workplace monitor is always BBZ-OS
