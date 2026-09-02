# Threat model

Roadmap **E23-10** (partial — the trust boundaries that exist today; the
Agent / BKU-session boundary is stubbed pending Epic 09/10). MASTER_PROMPT
§28.3. Companion: `pentest-checklist.md`, `dpia-input.md`.

STRIDE = Spoofing, Tampering, Repudiation, Information disclosure, Denial of
service, Elevation of privilege.

## Trust boundaries

```
    ┌───────────┐  1   ┌──────────────┐  2   ┌────────────┐
    │  browser  ├──────┤   BBZ API    ├──────┤ PostgreSQL │
    │ (kiosk)   │ HTTPS│  (2 nodes)   │ TLS  │  (Patroni) │
    └───────────┘      └───┬───┬──────┘      └────────────┘
                        3  │   │ 4
                  ┌────────┘   └────────┐
              ┌───┴────┐          ┌─────┴──────────────┐
              │  etcd  │          │ integrations       │
              │  (DCS) │          │ (Cisco/Siedle/DWD/ │
              └────────┘          │  Weytec/Coda/…)    │
                                  └────────────────────┘
    ┌───────────┐  5 (Epic 09/10 — not built)
    │ BKU agent ├╌╌╌╌╌ BBZ API
    └───────────┘
```

## 1 · Browser ↔ BBZ API

| STRIDE | risk | control | status |
|---|---|---|---|
| S | session theft / impersonation | HS256 access JWT (900 s) + opaque refresh (hashed at rest), server-side session store with revocation; `HttpOnly` + `Secure` + `SameSite=Lax` cookies | done (E02-05) |
| S | forged login | Argon2id, per-account lockout (5/15 min), rate limit `login` 10/60 per IP | done (E02-03, E23-04) |
| T | CSRF on cookie writes | `CsrfMiddleware`: `SameSite=Lax` + session-bound double-submit token + Origin/Referer allow-list; structural (contract test) | done (E23-05) |
| T | over-posting / oversized body | every write body `extra="forbid"` (contract test); `BodyLimitMiddleware` 413 @ 1 MiB before routing | done (E23-06) |
| R | "I never did that" | every critical action → append-only `audit_events`, now hash-chained | done (E04, E23-09) |
| I | secrets in responses / logs / traces | `redaction.scrub` on logs + spans; DTMF codes encrypted at rest, never logged; error envelope carries no internals | done (E17-06, E22-01/03) |
| D | request flood | per-endpoint rate limits (login/mfa/password-reset/webhook); WAF/edge DDoS is the reverse proxy's job (documented boundary) | partial — edge is deployment |
| E | horizontal / vertical priv-esc | server-side RBAC on **every** `/api/v1` write (contract test); scoped grants + Rule-DSL conditions can only narrow; MFA step-up on the most sensitive permissions | done (E02-07, E21-05/07) |

**Residual**: TLS termination + HSTS/CSP is the edge (Caddy baseline exists,
E06-12; strict CSP with nonces is E23-03, blocked on the Vue build). No
per-request API bucket — deliberate (abuse-prone endpoints are covered
explicitly).

## 2 · BBZ API ↔ PostgreSQL

| STRIDE | risk | control | status |
|---|---|---|---|
| S | rogue client connects to the DB | DB password is a deploy secret in the DSN; `preflight.sh` refuses a passwordless DSN; network-isolated in the compose/node topology | done (E24-03) |
| T | audit / event tampering | `audit_events` + `domain_events` append-only (`BEFORE UPDATE OR DELETE` trigger, any client); hash chain detects a `session_replication_role=replica` bypass or a doctored restore | done (E04-10, E23-09) |
| I | backup exfiltration | every backup `gpg --encrypt`, mode 0600, **asymmetric** (private key offline); `bbz-backup` user; `$BACKUP_DIR` 0700 | done (E06-14) |
| D | connection exhaustion | bounded async pool (`database_pool_size`); Patroni promotes a standby on primary loss (RTO per ADR-0021) | done |
| E | SQL injection | SQLAlchemy Core/ORM parameterised everywhere; `db.statement` spans are parameterised, never bound values | done |

## 3 · BBZ API ↔ etcd (DCS)

| STRIDE | risk | control | status |
|---|---|---|---|
| S / T | forged leader lease / config write | etcd **mTLS** — `client-bbz-app` cert, CA-verified (`deploy/etcd/gen-certs.sh`); `preflight.sh` checks the three cert files | done (E06-03) |
| D | quorum loss halts failover | 3-member cluster (2 nodes + witness); `BbzQuorumLost` alert | done (E06-08, E22-06) |
| E | witness runs domain services | quorum compose is **etcd-only** — asserted in CI | done (E06-08) |

## 4 · BBZ API ↔ integrations

| STRIDE | risk | control | status |
|---|---|---|---|
| S | spoofed inbound webhook (telephony/Coda/Siedle) | service-account **bearer** token with a narrow permission (`calls.ingest_provider_events`); the event carries only normalised handles, never a vendor object id; rate limit `webhook` 240/60 | done (E11-03, E23-04) |
| T | duplicate/replayed provider event → double action | provider inbox + dedupe; the door-open flow is idempotent (a duplicate ring never triggers a second unlock) | done (E11-03, E17-04) |
| I | DTMF door code leak | code encrypted at rest (Fernet), audited by profile id **not** value, filtered from every log/trace/audit sink | done (E17-02/06) |
| I | vendor object ids crossing the boundary | SDK contract: only normalised `camera_id` / handle types cross; enforced by the integration-SDK layering (import-linter) | done (E16-02) |
| D | a hung integration stalls the API | every probe is `asyncio.gather` with a timeout; `integration_health` + `BbzIntegrationDown` alert; a failed refresh keeps last-good data | done (E22-05) |
| E | an integration reaches into core | `import-linter`: core never imports concrete integrations; api/domain never import the SDK directly | done (E01) |

**Blocked/vendor**: the *real* transports (JTAPI, SIP, Coda, Weytec) are
interface-only or `mock: true` pending vendor docs — see `docs/roadmap-status.md`.

## 5 · BKU agent ↔ BBZ API — **not built (Epic 09/10)**

The design (`.ai/SECURITY.md` §"Agent / remote control security") is fixed:
short-lived enrollment token → unique device cert (mTLS, E09-08 / E23-02); no
arbitrary shell/URL/executable — only an allowlisted catalog (E10-07/12);
remote logout/restart needs a dedicated permission + explicit confirmation +
audit; commands carry `command_id` + nonce + expiry + generation and are
replay-protected (E10-13); browser→agent direct trust is forbidden — every
command is routed and authorised by the server. **Threat analysis of this
boundary is completed with Epic 10** (the fuzzing is E23-11).

## Assumptions

- The reverse proxy terminates TLS and adds HSTS/CSP/security headers.
- The two app nodes and the witness are on a trusted management network.
- The GPG backup private key and any offline operator keys are held outside the
  BBZ servers.
- Operators are authenticated humans; a compromised operator workstation is out
  of scope for this model (it is the BKU-agent / endpoint-hardening concern).
