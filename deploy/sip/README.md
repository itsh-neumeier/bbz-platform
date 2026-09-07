# `deploy/sip/` — Asterisk lab PBX (E13-08)

A throwaway Asterisk 20 container for the `telephony_sip` provider's integration
tests (roadmap **E13-08**, ADR-0023). It is **not** part of any production
topology and is never deployed — a real BBZ site points `telephony_sip` at
*their* Asterisk from the admin UI, with the ARI password encrypted at rest
(**ADR-0033**).

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
| `asterisk/Dockerfile` | `debian:bookworm-slim` + `apt-get install asterisk`, runs as the non-root `asterisk` user |
| `asterisk/etc/http.conf` | the built-in HTTP server (ARI transport) on `:8088` |
| `asterisk/etc/ari.conf` | ARI enabled, user `bbz-lab` |
| `asterisk/etc/extensions.conf` | `[bbz-sip]` hands calls to `Stasis(bbz-sip)`; `[bbz-lab]` parks a leg so ARI can drive the other |
| `asterisk/etc/pjsip.conf` | one real UDP endpoint (`bbz-lab-phone`) for the registration-loss scenario |
| `asterisk/etc/modules.conf` | `autoload=yes` minus CDR/`chan_sip` noise |

Everything else is the Debian package default.

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
