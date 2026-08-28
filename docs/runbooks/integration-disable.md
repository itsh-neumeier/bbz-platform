# Runbook: disable a misbehaving integration

> Stub — the admin surface (`integrations.enable_disable`, diagnostics) is built
> in Phase 1+.

## Goal

Contain a failing or noisy integration without redeploying the platform.

## Steps (target behavior)

1. Admin with `integrations.enable_disable` opens Integrations → the integration.
2. Set to **disabled** (or **mock mode** for controlled testing).
3. The integration host stops routing events to/from it; its provider health
   shows `disabled`.
4. Core domain keeps running. Inbound external events that would have matched are
   parked in the unmapped/queued diagnostics list, not lost.
5. Record the reason; the action is audited.

## Notes

- Disabling `coda_video` must not block the Siedle door-open call workflow — the
  camera side effect is decoupled (ADR-0006).
- Disabling a telephony provider stops call control; document the operational
  fallback (Cisco endpoint direct use) before doing this in production.
