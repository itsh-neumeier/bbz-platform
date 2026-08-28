# telephony_sip (PLACEHOLDER — no code)

Vendor-neutral SIP telephony provider. **Not implemented in Phase 0** (Phase 5).

- Must **not** depend on Cisco JTAPI or `telephony_cucm` (ADR-0002 §11/§8.17).
- Purpose: simple SIP trunks, alternative PBX, lab/test, migration/fallback,
  other vendors.
- The core always speaks the normalized `TelephonyProvider` interface.
- Concrete SIP stack (e.g. Asterisk / FreeSWITCH gateway vs. library) is chosen
  by ADR at the start of Phase 5.
