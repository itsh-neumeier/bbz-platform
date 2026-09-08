# ADR-0034: SIP trunk (ITSP) config — BBZ stores it, generates the Asterisk config, a sync script delivers it

## Status
Accepted (2026-09-07, roadmap E13-09 / #803)

## Context

Epic 13 gave BBZ the `telephony_sip` provider (Asterisk via ARI, ADR-0023) and a
DB-backed, UI-managed **control-plane** config (ADR-0033): where BBZ's Asterisk
is, the ARI credentials, the Stasis app, the BBZ line → endpoint map. That is
the link **between BBZ and Asterisk**.

It does **not** cover the link **between Asterisk and the telephone network** —
the SIP trunk to an ITSP (LEONET, Telekom DeutschlandLAN SIP Trunk / CompanyFlex,
…) that makes real phone numbers ring. E13-02 explicitly scoped that out
("Nicht im Scope: Produktive SIP-Trunks (Kunde)"). The product now needs it: a
BBZ site must be able to enter its trunk credentials and its public numbers in
the admin UI and have incoming PSTN calls arrive in BBZ.

### Prior art the operator already runs

`itsh-neumeier/itsh-neumeier-astm` — a standalone WebGUI that keeps trunk state
in SQLite and renders `pjsip.conf` + `extensions.conf` **deterministically** from
it (`app/generator.py`), then writes the files and runs `asterisk -rx "pjsip
reload"`. Provider defaults for LEONET are baked in; other providers are entered
by hand. Numbers carry their own SIP username/password (the German per-MSN
registration model); inbound calls are identified by the provider SBC IP
(`type=identify`).

### The delivery question

How does the trunk config reach the Asterisk box?

- **PJSIP Realtime (ARA)** — Asterisk reads endpoints/auths/registrations from a
  database directly. Rejected: it puts DB credentials and a DB network path on
  the PBX, and the effective config is not inspectable as a file.
- **Generated config + a sync script** (chosen) — BBZ renders the config and
  exposes it over an authenticated admin endpoint; a small script on the
  Asterisk box fetches it, writes it atomically, and reloads. The operator can
  also just copy it out of the UI once. This matches the standalone tool the
  operator already trusts, keeps the rendered result diffable and
  version-pinnable, and keeps BBZ↔PBX coupling to "an HTTPS GET with a token".

## Decision

**BBZ stores SIP trunk definitions and public numbers in its DB, generates the
Asterisk trunk config from them, and delivers it to the Asterisk box with a sync
script (or a copy-paste from the UI). No PJSIP Realtime, no DB path from the
PBX.**

### 1 · New domain tables (migration 0057) — not settings keys

- **`sip_trunks`** — one row per ITSP trunk:
  `trunk_id` (slug PK), `provider` (`leonet` | `telekom` | `generic` — drives
  only the UI preset, never behaviour), `display_name`, `enabled`,
  `sip_server` (registrar / proxy host), `sip_port`, `transport`
  (`udp` | `tcp` | `tls`), `outbound_proxy`, `from_domain`, `register` (bool),
  `auth_username`, `auth_password_ciphertext`, `match_hosts` (comma CIDR list for
  inbound `type=identify`), `codecs`, `dtmf_mode`, `caller_id_e164` (default
  outbound CLI), `updated_by`, timestamps.
- **`sip_numbers`** — one row per public DID / MSN:
  `e164` (PK), `trunk_id` (FK → `sip_trunks`, CASCADE), `bbz_line_id` (the
  `Stasis(bbz-sip,<arg>)` argument for an inbound call on this number; defaults
  to the E.164), `label`, `register` (per-number registration — the LEONET
  per-MSN model), `auth_username`, `auth_password_ciphertext` (both empty →
  the trunk's auth is used), `enabled`, timestamps.

### 2 · Trunk auth passwords are Fernet-encrypted at rest

Same mechanism and key as the ARI password (ADR-0033):
`bbz_core.infra.sip_secrets`, key `BBZ_SIP_ENCRYPTION_KEY`. A password enters
only in a `PUT`/`POST` body over TLS, is encrypted immediately, and is **never**
returned by `GET`, logged, or written to an audit row — `GET` reports
`auth_password_configured: true|false`. Decryption happens in-process only, at
config-render time.

### 3 · Config generation is a pure service

`SipTrunkConfigService.render_asterisk_config()` → `{pjsip, extensions}`,
mirroring the standalone `generator.py` but targeting BBZ:

- `pjsip` → `[global]` + one `[transport-*]` per transport in use + per trunk a
  `type=endpoint` / `type=aor` / `type=auth` (+ `type=registration` if `register`,
  + `type=identify` if `match_hosts`); per number with its own auth an extra
  `type=auth` (+ `type=registration`).
- `extensions` → a `from-<trunk_id>` context per trunk that normalises the
  inbound DID to E.164 and hands the call to **`Stasis(bbz-sip,<bbz_line_id>)`**
  (BBZ then drives it over ARI — no `Dial`, no UniFi paths).

The rendered text is meant to land in Asterisk `#tryinclude` files
(`pjsip_bbz_trunks.conf`, `extensions_bbz_trunks.conf`) alongside the box's base
config, not to replace `pjsip.conf`.

### 4 · Delivery — authenticated export + a sync script

- `GET /api/v1/admin/telephony/sip/asterisk-config?part=pjsip|extensions|all`
  → `text/plain`, **`Cache-Control: no-store`**, gated `integrations.configure`.
  The response **contains the trunk passwords in cleartext** — PJSIP `type=auth`
  requires it, and every Asterisk trunk config on earth does. Therefore the
  rendered config is **never written to BBZ's disk, logged, or audited**; it is
  streamed to the response only.
- `deploy/sip/sync-trunk-config.sh` — logs in with a supplied least-privilege
  account, fetches both parts, writes them `0600` atomically into the Asterisk
  config dir, runs `pjsip reload` + `dialplan reload`. Lab / CI use it directly;
  production runs it from cron / a systemd timer, or an operator pastes the UI
  output onto an air-gapped box.
- A long-lived machine token / service account for the script is **out of scope**
  here (ADR-0019 territory) — until then it is account credentials or the paste
  path.

### 5 · Admin API + audit

Under `/api/v1/admin/telephony/sip`, all gated `integrations.configure`:
`GET/PUT/DELETE .../trunks/{id}`, `GET/PUT/DELETE .../numbers/{e164}`,
`POST .../trunks/{id}/test` (registration state via ARI `GET /endpoints` +
`GET /registrations` on the active gateway). Every write emits one critical
audit row — `SIP_TRUNK_CONFIGURED` / `SIP_TRUNK_REMOVED` /
`SIP_NUMBER_CONFIGURED` / `SIP_NUMBER_REMOVED` — carrying the id and a redacted
non-secret before/after diff, **never** a password.

### 6 · Provider presets are UI-only, non-authoritative

The UI offers LEONET / Telekom / generic presets that pre-fill **technical
defaults only** (transport, ports, from-domain shape, registration on, DTMF
mode, codecs). LEONET's values come from the operator's standalone tool; the
Telekom values are the widely-documented public DeutschlandLAN SIP Trunk
parameters (`reg.sip-trunk.telekom.de`, TCP). Both carry a visible
"gegen Auftragsbestätigung / Provider-Doku prüfen" banner. **No credentials, no
customer-specific realms or proxies are shipped** — the operator enters those
from their order confirmation. This is not an "external API contract": it is a
convenience default the operator confirms.

## Consequences

- A site admin configures the trunk and its numbers end to end from
  `/admin/telefonie`, gets the Asterisk config from the same screen, and either
  runs the sync script or pastes it once.
- `BBZ_SIP_ENCRYPTION_KEY` now also protects the trunk auth passwords — one more
  set of secrets under the existing key, no new key.
- BBZ renders config for a system it does not own. The contract is the rendered
  text: if Asterisk rejects it, the operator sees it on `pjsip reload`. BBZ does
  not validate against a live Asterisk beyond the existing "test connection".
- The generated files are `#tryinclude`d; a site that hand-manages `pjsip.conf`
  can still paste just the BBZ sections.
- Outbound calls *through* a trunk (choosing a trunk + CLI for `dial`) are a
  follow-up — this ADR wires inbound ("real numbers ring in BBZ") and renders an
  outbound context, but the `dial` verb still originates `PJSIP/<line>`.
- When the ADR-0019 secret store lands, the trunk ciphertext columns move behind
  `SecretProvider` with the other at-rest secrets (ADR-0033 already says this for
  the ARI password).

## Alternatives considered

- **PJSIP Realtime (ARA).** Rejected — DB credentials + DB reachability on the
  PBX, effective config not a file, and it couples BBZ's schema to Asterisk's
  realtime column expectations.
- **BBZ opens an AMI/ARI connection and pushes `pjsip.conf` via the Asterisk
  config API.** Asterisk has no complete "replace pjsip.conf" API; the ARI
  `asterisk/config` surface is partial and version-sensitive. The file + reload
  path is what every ITSP integration guide uses.
- **Keep trunk config out of BBZ entirely — operator manages Asterisk by hand.**
  Rejected per the product ask (everything UI-driven) and because the operator
  already built a tool to avoid exactly that.
- **A second encryption key for trunk secrets.** No security gain over reusing
  `BBZ_SIP_ENCRYPTION_KEY`; one more key to distribute and rotate.
