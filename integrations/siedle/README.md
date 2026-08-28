# siedle (PLACEHOLDER — no code)

Siedle door-station control. **Not implemented in Phase 0.**

Design fixed by **ADR-0004** and `.ai/INTEGRATIONS_SIEDLE.md`:

- No invented Siedle HTTP API. Initial control runs **through the telephony
  provider** using a configurable **DTMF/MFV profile** during the call.
- The DTMF code is a **secret / configuration value** — never hardcoded, never
  written to plaintext audit logs. Audit records the action-profile id only.
- Each door station is a `technical_endpoint`, not a phonebook contact.
- Ring flow → `DOORBELL_RINGING` → camera request (decoupled) + bottom-right
  popup → `Öffnen`: authorize `door.open`, answer if required, wait CONNECTED,
  send DTMF profile, post-delay, hang up, audit. Idempotent — never a double
  unlock on a duplicated telephony event.
