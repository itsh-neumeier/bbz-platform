# telephony_sip

Vendor-neutral SIP telephony provider — simple SIP trunks, alternative PBX,
lab/test, migration/fallback, other vendors. The core only ever speaks the
normalized `TelephonyProvider` interface.

**Independent of Cisco.** Must not import `integrations.telephony_cucm` or any
Cisco-JTAPI binding (ADR-0002 §8.17) — enforced by the import-linter contract
*"telephony_sip is independent of Cisco CUCM / JTAPI"*.

## Status — scaffold (E13-01)

Present now: `manifest.json`, `config_schema.json`, and a protocol-conformant
adapter **stub** (`adapter.py`). Lifecycle + read queries return safe
empty/unknown values so the integration host can register and health-check the
provider; every control command raises `SipNotConfiguredError`.

Still to come:

| Issue | What |
|---|---|
| E13-02 | ADR-0023: Asterisk (ARI) vs. FreeSWITCH (ESL); minimal test gateway in compose |
| E13-03 | SIP adapter → normalized provider interface |
| E13-04 | registration + call events → normalized events |
| E13-05 | call control (dial / answer / hangup / hold / transfer) |
| E13-06 | DTMF (RFC 2833 / SIP INFO) → `send_dtmf` capability (profile only) |
| E13-07 | config schema + secrets |
| E13-08 | integration tests against a containerized test PBX |

## Config

See `config_schema.json`. Credentials are a `credentials_secret_ref` into the
secret store — never inline. The raw DTMF code is a secret too; only the profile
id is ever handled in this adapter (ADR-0004).
