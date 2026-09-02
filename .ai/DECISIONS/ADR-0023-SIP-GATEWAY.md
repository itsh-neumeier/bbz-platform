# ADR-0023: SIP/CTI gateway — Asterisk ARI

## Status
Proposed (2026-09-02, review E13-02 / #271)

## Context
Epic 13 adds an **optional** SIP telephony provider (`telephony_sip`), parallel
to and independent of the Cisco CUCM path (ADR-0002 §8.17, enforced by the
`telephony_sip` ↛ `telephony_cucm` import contract). It is for a lab / test
setup and for sites that run SIP rather than CUCM. MASTER_PROMPT §8.17 already
narrows the gateway to **Asterisk or FreeSWITCH**; this ADR picks one.

The provider has to satisfy the full `TelephonyProvider` protocol — answer /
dial / hangup / hold / resume / transfer / `send_dtmf` / monitoring — and feed
the normalized pipeline: gateway call events → `inbound_signal.v1`
(E13-04 / E15-04) → provider inbox → trigger engine. DTMF must go out as
RFC 2833 or SIP INFO (E13-06); the digit sequence itself is resolved and held by
BBZ (ADR-0025), the adapter only emits it.

Constraints that matter here:
- The BBZ Leitstelle is small — a handful of operators, low concurrent call
  volume. This is not a carrier-scale workload.
- `bbz-api` already speaks async HTTP + WebSocket + JSON (httpx, the SSE stream).
  It does **not** speak any bespoke telephony protocol.
- `integrations/telephony_sip/config_schema.json` already carries
  `gateway.kind ∈ {asterisk_ari, freeswitch_esl}` and
  `dtmf_transport ∈ {rfc2833, sip_info}`, pending this decision.

## Decision
The `telephony_sip` adapter targets **Asterisk via ARI** (the Asterisk REST
Interface): REST for channel control, a WebSocket for the event stream, JSON on
both. `gateway.kind = "asterisk_ari"` is the supported default.

- Calls are handed to a **Stasis application** in the Asterisk dialplan; the
  adapter owns the channel from `StasisStart` and drives it over
  `POST /channels/{id}/…` (answer, hold, redirect, hangup) and
  `POST /channels/{id}/play` / `…/dtmf`.
- The event mapper (E13-04) translates ARI events to `inbound_signal.v1`:
  `StasisStart` / `ChannelStateChange(ringing)` → `CALL_RINGING`,
  `ChannelStateChange(up)` → `CALL_ANSWERED`, `ChannelHangupRequest` /
  `StasisEnd` → `CALL_ENDED`, `ChannelDtmfReceived` → the DTMF signal. Only
  allow-listed fields cross the edge; ARI channel ids and vendor detail are
  dropped.
- Connection config: `gateway.host` / `port` / `tls`, API user + password from
  `credentials_secret_ref` (E13-07 — never inline). The adapter opens one
  WebSocket per instance and reconnects with backoff; a dropped socket makes
  `health()` report `degraded`.
- `dtmf_transport` stays `rfc2833` by default. ARI's `channels/{id}/dtmf`
  abstracts the on-the-wire form; the setting is passed to Asterisk config, not
  branched on in the adapter.
- `freeswitch_esl` remains a **documented, non-default** value in the config
  schema. Choosing it later is a separate ESL client + a second event mapper;
  nothing else in the design changes.

The lab test gateway (E13-03+) is an `asterisk` container in a `sip` compose
profile: a minimal `ari.conf` + `http.conf` + a Stasis-app dialplan entry, and
SIPp (or a softphone) for the compose smoke test.

## Consequences
- **Easier:** no new wire protocol. The adapter is an async REST client plus a
  WebSocket consumer — both already idioms in this codebase. ARI's channel
  ownership model is a direct fit for `TelephonyProvider`'s per-call verbs.
  Plenty of public ARI + REST integration examples.
- **To maintain / watch:** an Asterisk container image and its config
  (`ari.conf`, `http.conf`, dialplan) as part of the deploy set; ARI's
  WebSocket needs a reconnect/resync path (a missed event during a drop must not
  strand a call — reconcile against `GET /channels` on reconnect).
- **Cost accepted:** FreeSWITCH's higher call-throughput ceiling is given up.
  Irrelevant at this scale; revisit only if a site's call volume changes the
  picture.
- The config schema and the `SipTelephonyProvider` scaffold (E13-01) need no
  shape change — this fills in the `asterisk_ari` branch.

## Alternatives considered
**FreeSWITCH via ESL** — very complete event set, higher performance, strong at
scale. But the Event Socket is a bespoke TCP protocol (a client library and
framing to build and keep working), the config surface is larger (XML dialplan /
mod_lua), and there is no throughput requirement here. Kept as the documented
fallback in `config_schema.json`.

**Asterisk AMI instead of ARI** — the older line-based action/response protocol.
ARI supersedes it for external application control and has the cleaner
channel-ownership (Stasis) model. No reason to choose AMI for greenfield work.

**In-process SIP stack** (a PJSIP/SIP binding inside `bbz-api`, no gateway) —
pulls SIP signaling, RTP, NAT traversal and codec handling into the API process:
a large, fragile surface and an availability risk for the whole API. §8.17
already frames this as a gateway. Rejected.

## What would change this decision
An existing customer FreeSWITCH deployment to integrate with; a SIP trunk
provider that specifically recommends one stack; or a feature only FreeSWITCH
offers becoming a requirement. None of these are on the table today.
