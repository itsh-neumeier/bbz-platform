# telephony_sip

Vendor-neutral SIP telephony provider — simple SIP trunks, alternative PBX,
lab/test, migration/fallback, other vendors. The core only ever speaks the
normalized `TelephonyProvider` interface.

**Independent of Cisco.** Must not import `integrations.telephony_cucm` or any
Cisco-JTAPI binding (ADR-0002 §8.17) — enforced by the import-linter contract
*"telephony_sip is independent of Cisco CUCM / JTAPI"*.

## Status — ARI transport (E13-03)

| Issue | What | State |
|---|---|---|
| E13-02 | ADR-0023: Asterisk (ARI) vs. FreeSWITCH (ESL) | done |
| E13-03 | ARI transport (`ari.py`) — REST + WS, health probe | **done** |
| E13-04 | ARI events → normalized `inbound_signal.v1` | next |
| E13-05 | call control (dial / answer / hangup / hold / transfer) | next |
| E13-06 | DTMF (RFC 2833 / SIP INFO) → `send_dtmf` | next |
| E13-07 | config schema + secrets | schema done; DB config = ADR-0033 |
| E13-08 | integration tests against a `sip`-profile Asterisk container | next |

`ari.py` is the transport: `AriClient` opens a `httpx` REST session + an ARI
event WebSocket (`Authorization: Basic` header, never credentials in a URL),
reconnects with backoff. With a `gateway` config block the adapter's `health()`
probes `GET /ari/asterisk/info`; without one it stays a scaffold. The event
mapper and the `TelephonyProvider` control verbs still raise
`SipNotConfiguredError`.

## Config

See `config_schema.json`. **Production** stores the gateway config — including
the ARI password, encrypted at rest — in the DB, managed from the admin UI
(**ADR-0033**). **Dev / CI / file-provisioned** instances may pass
`credentials` inline or a `credentials_secret_ref` into the secret store. The
raw DTMF code is a secret too; only the profile id is handled here (ADR-0004).
