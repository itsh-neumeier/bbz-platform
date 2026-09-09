# `deploy/sip/` — Asterisk lab PBX (E13-08) + trunk config sync (E13-09/11)

A throwaway Asterisk 20 container for the `telephony_sip` provider's integration
tests (roadmap **E13-08**, ADR-0023). It is **not** part of any production
topology and is never deployed — a real BBZ site points `telephony_sip` at
*their* Asterisk from the admin UI, with the ARI password encrypted at rest
(**ADR-0033**).

`sync-trunk-config.sh` (E13-09, **ADR-0034**) is the one piece meant to run on a
real Asterisk box too: it pulls the SIP-trunk config BBZ generates from
`/admin/telefonie` and reloads Asterisk.

## Run it

```sh
cp .env.example .env                       # repo root
docker compose --profile sip up -d --build
```

ARI is then reachable at `http://127.0.0.1:8088/ari/` (REST) and
`ws://127.0.0.1:8088/ari/events?app=bbz-sip` (event stream), user `bbz-lab`.

```sh
curl -s -u bbz-lab:bbz-lab-not-a-secret http://127.0.0.1:8088/ari/asterisk/info | jq .
```

## What's in the image

| File | Purpose |
|---|---|
| `asterisk/Dockerfile` | `ubuntu:24.04` + `apt-get install asterisk curl`, runs as the non-root `asterisk` user. Build context is `deploy/sip/` |
| `asterisk/entrypoint.sh` | if `BBZ_API` is set, runs `sync-trunk-config.sh` once ~8 s after boot; then `exec asterisk -f` |
| `asterisk/etc/http.conf` | the built-in HTTP server: ARI on `:8088` (plain) + `wss://` on `:8089` (TLS, self-signed cert generated in the image) for the operator softphone |
| `asterisk/etc/ari.conf` | ARI enabled, user `bbz-lab` |
| `asterisk/etc/extensions.conf` | `[bbz-sip]` hands calls to `Stasis(bbz-sip)`; `[bbz-lab]` parks a leg; `#tryinclude extensions_bbz_trunks.conf` |
| `asterisk/etc/pjsip.conf` | UDP + TCP transports, one real endpoint (`bbz-lab-phone`); `#tryinclude pjsip_bbz_trunks.conf` (trunk `[transport-wss]` + operator endpoints come from there) |
| `/etc/asterisk/keys/asterisk.{crt,key}` | self-signed cert for `wss://`, **lab only** — a real site drops a real cert at these paths |
| `asterisk/etc/modules.conf` | `autoload=yes` minus CDR/`chan_sip` noise |
| `sync-trunk-config.sh` | fetch BBZ's generated trunk config, write it `0600`, `pjsip`/`dialplan reload` |

Everything else is the Ubuntu package default.

## SIP trunks (LEONET / Telekom) — E13-09, ADR-0034

BBZ stores the trunk + the public numbers (`/admin/telefonie` → "SIP-Trunks")
and generates two Asterisk fragments; `sync-trunk-config.sh` delivers them:

```sh
BBZ_API=https://bbz.example:8443 \
BBZ_USER=sip-sync BBZ_PASS=… \
CURL_OPTS='--cacert /etc/ssl/bbz-ca.pem' \
  ./sync-trunk-config.sh
```

It writes `pjsip_bbz_trunks.conf` + `extensions_bbz_trunks.conf` into
`$ASTERISK_ETC` (`#tryinclude`d by the base config) and reloads. The fetched
files **contain the trunk auth passwords in cleartext** (PJSIP `type=auth` needs
them) — they land `0600` and BBZ never writes/logs/audits the rendered text. An
operator who won't give the box API access can paste the same text from the
admin screen instead.

For the lab, set `BBZ_LAB_API` / `BBZ_LAB_USER` / `BBZ_LAB_PASS` in `.env` and
the `asterisk` service pulls on start.

## WebRTC operator softphone — E13-11, ADR-0035

An operator's browser registers to Asterisk over `wss://` and BBZ bridges their
audio leg into the call over ARI. Setup:

1. Admin creates the operator's endpoint:
   `PUT /api/v1/admin/telephony/sip/webrtc/{user_id}` `{"enabled": true}`.
2. Set `BBZ_SIP_WEBRTC_WS_URL` on the `api` service, e.g.
   `wss://127.0.0.1:8089/ws` for the lab (optionally
   `BBZ_SIP_WEBRTC_ICE_SERVERS=stun:stun.l.google.com:19302`).
3. Run `sync-trunk-config.sh` — the generated `pjsip_bbz_trunks.conf` now also
   carries `[transport-wss]` + a `type=endpoint`/`auth`/`aor` per operator.
4. The web client fetches `GET /api/v1/telephony/webrtc-credentials` on login and
   registers automatically; the comms sidebar shows the softphone status.

The lab's `wss://` uses a **self-signed** cert — the browser must have accepted
it (visit `https://127.0.0.1:8089/` once, or serve the web app over the same
cert in dev). `pjsip show contacts` shows the registered softphone.

### Media path on Docker Desktop (#834)

Signalling works out of the box, but on Docker Desktop (Windows/macOS) Asterisk
runs in a VM whose IP the host browser can't reach, so a **direct ICE pair
never forms** and calls have no audio. The `sip` profile ships a **`coturn`**
service both sides relay through:

- `entrypoint.sh` writes `turnaddr`/`turnusername`/`turnpassword` into `rtp.conf`
  (resolving the `coturn` service) so Asterisk relays too — and rewrites its ICE
  host candidate to **`BBZ_ICE_HOST_IP`** (set the host's LAN IP in `.env`).
- Point the browser at it: on the `api` service set
  `BBZ_SIP_WEBRTC_TURN_URL=turn:127.0.0.1:3478`,
  `BBZ_SIP_WEBRTC_TURN_USERNAME=bbzturn`, `BBZ_SIP_WEBRTC_TURN_PASSWORD=bbzturn`
  (matches coturn's `--user`).

A real deployment (Asterisk on a routable host) needs none of this — drop the
`coturn` service and leave the `BBZ_SIP_WEBRTC_TURN_*` / `BBZ_ICE_HOST_IP` vars
unset.

## Music on hold — E13-12, #817

Upload WAVs (`POST /api/v1/admin/telephony/moh`, raw body, `?name=`), then
assign per line via `PUT /admin/telephony/sip/lines/{id}` —
`ring_moh_file_id` plays while a caller waits for an operator,
`hold_moh_file_id` while an established call is on hold. `sync-trunk-config.sh`
fetches `?part=musiconhold` into `musiconhold_bbz.conf` and pulls each
referenced WAV (via `GET .../moh/manifest` + `GET .../moh/{id}/download`) into
`$MOH_DIR/<id>/moh.wav`, then `moh reload`. Deleting a file still used by a line
is a 409. The bytes live in `$BBZ_MOH_DIR` on the BBZ node, never the DB.

## The credential

`ari.conf` / `pjsip.conf` carry a **well-known throwaway** password
(`bbz-lab-not-a-secret`). It is allow-listed in `.gitleaks.toml` for
`deploy/sip/` exactly like the `bbz:bbz` dev-Postgres default. Nothing about
this container is a secret; a production ARI user is created by the operator and
stored encrypted (ADR-0033), never committed.

## Tests

`integrations/telephony_sip/tests/test_sip_integration.py` — skipped unless an
ARI endpoint is reachable (`BBZ_TEST_ARI_HOST`, default `127.0.0.1`). Run
nightly by `.github/workflows/sip-nightly.yml` (`continue-on-error` until shaken
out on real hardware, same policy as `ha-nightly.yml`). Scenarios: incoming call
→ answer → hold → resume → DTMF → hangup, an outbound `dial`, and the health
probe. See `.ai/TESTING.md`.
