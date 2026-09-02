# Roadmap status — what is done, what is blocked, and why

Companion to `.ai/ROADMAP.md` and `.ai/CURRENT_STATE.md`. It exists so **no
roadmap issue is an undocumented gap**: every not-yet-merged issue has a status,
a blocker, and — where one exists — the slice that could still be done now.

_Last swept: 2026-09-02._

## Legend

| mark | meaning |
|---|---|
| **done** | merged to `main` |
| **backend-done** | server + tests + API merged; only the UI is missing (→ Epic 07) |
| **blocked/toolchain** | needs a Node / Electron / Go build environment this repo's CI does not provide |
| **blocked/vendor** | needs a real vendor API/credential (Cisco CUCM, Weytec, Coda, Siedle, Entra, LDAP) that must not be invented |
| **blocked/dep** | waiting on another blocked issue |
| **in progress** | partially merged this phase |

---

## Complete

| epic | status |
|---|---|
| 01 Repository Foundation | **done** |
| 02 Identity / RBAC | **done** (14/14) |
| 03 Event Core | **done** (16/16) |
| 04 Audit / Domain Events | **done** — append-only trigger + outbox/inbox; hash chain added in E23-09 |
| 05 EPK Workflow Engine | **done** — AND/OR/XOR, publish/version-pin, simulation |
| 06 HA Cluster | **done** — Patroni/etcd, leader election, rolling-update tooling, backup scripts (E06-14), HA harness (E06-11) |
| 17 Siedle door control | **backend-done** (only E17-xx UI) |
| 18 DWD weather | **backend-done** — framework + 3 live adapters + fixtures; only E18-09 UI |
| 19 Weytec monitor routing | **backend-done 9/10** — `monitor_weytec` is interface-only pending the Weytec API (`docs/integrations/weytec-monitor-pending.md`) |
| 20 Archive / Postprocessing | **backend-done** |
| 21 Enterprise Authentication | **backend-done** (E21-01..08) — OIDC/LDAP/MFA/WebAuthn/RBAC/linking; real IdP/dir params are an open dependency |
| 22 Monitoring / Observability | **done** (7/7) — tracing, metrics, log pipeline, health, integration-health, alerts, collector+dashboards |

---

## Backend-done, UI is Epic 07

These epics are fully functional on the server (schema, services, API, tests);
the operator UI is the only missing piece and every UI issue is an Epic-07 row.

| epic | UI issues waiting on Epic 07 |
|---|---|
| 11 Telephony Core | E11-13, E11-14, E11-15 (UI), E11-16 (Playwright) |
| 13 SIP Provider | UI + the real SIP transport (E13-06, blocked/vendor) |
| 14 Contacts / Call Priorities | E14-07..10 (UI) |
| 15 Technical Trigger Engine | E15-14 (UI) |
| 16 Coda Video | E16-xx UI; alarm/camera transport is `mock: true` pending Coda docs (blocked/vendor) |

---

## Epic 07 · Web UI / PrimeVue — **blocked/toolchain** (1/19)

- **E07-01 done**: `docs/mockup-parity-checklist.md` tracks every §13 feature →
  issue → status.
- **E07-03 partial**: the app shell (`apps/web/`) exists — `AppShell`, `TopBar`
  (clock), `SidebarLeft`, `CommsSidebar`, theme tokens (light/dark), i18n (DE),
  Pinia session store, a typed API client, `tests/shell.spec.ts`.
- **E07-02, 04..19 blocked**: 17 Vue components + Playwright E2E. The repo has no
  Node dev loop wired for agentic work and CI's `frontend` job is
  `continue-on-error`. Also gated: **#14** (deliberate frontend dependency
  major-upgrade pass — `apps/web` currently has 5 npm advisories; see
  `docs/security/vulnerability-scanning.md`).
- **Doable slice without a full Node session**: pin `primevue` and
  `@primevue/themes` to the same exact version in `apps/web/package.json` (they
  drift today), add `server.allowedHosts` for the compose/reverse-proxy hosts,
  commit a lockfile. Tracked under #14.

## Epic 08 · BBZ Desktop Client (Electron) — **blocked/toolchain**

All 7 issues need Node + Electron. `E08-07` (load-strategy ADR: server-build vs
bundle) is an open decision. Nothing shippable here without an Electron build
environment.

## Epic 09 · BBZ Client Agent (Go) — **blocked/toolchain** (1/10)

- **E09-01 done**: ADR-0009 Accepted — **Go**. Shared libs named (`discovery`,
  `outbox`, `commandenvelope`), workspace planned at `services/bbz-agents/`.
- **E09-02..10 blocked**: Windows service lifecycle, discovery/failover,
  encrypted cache, offline outbox, reconnect/idempotent sync, **device identity
  / cert enrollment (E09-08)** — the last is the dependency for **E23-02** mTLS.
- No Go toolchain in this environment.

## Epic 10 · BKU Agent — **blocked/dep** (schema-only)

- **E10-01, E10-02, E10-14 done**: `bku_agents` / `bku_agent_enrollments` /
  `bku_agent_commands`, `application_catalog` / `_scopes` schema + the BKU
  permission seed. The catalog-admin + consume APIs (E10-10/11) and the
  allowlist enforcement (**E10-12**) and command reliability (**E10-13**) —
  the two dependencies for **E23-11** — need the Go agent (Epic 09) and are
  blocked.

## Epic 12 · Cisco CUCM / JTAPI — **blocked/vendor**

All 20 issues are the separate Java `services/cucm-cti-gateway`. Needs
`jtapi.jar`, a Java toolchain, and the real CUCM version / CTI cluster config
(§8.18). `E12-01` (the gateway image) is the dependency for **E24-01** (complete
`release.yml`) and transitively **E23-12**, **E24-02**, **E24-04**.

---

## Epic 23 · Security Hardening — **in progress (7/13)**

| issue | status |
|---|---|
| E23-01 secret store | **done** (#677, ADR-0019) |
| E23-04 rate limiting | **done** (#678) |
| E23-05 CSRF | **done** (#679) |
| E23-06 input validation + payload cap | **done** (#680) |
| E23-07 scanning gates + exception process | **done** (#682) |
| E23-08 non-root container audit | **done** (#684) |
| E23-09 audit-log hash chain | **done** (#683) |
| **E23-02** TLS + internal mTLS | **blocked/dep** — API↔`cucm-cti-gateway` and Go-agent mTLS need E09-08 / E12-16. Internal PKI already exists for the DCS plane (`deploy/etcd/gen-certs.sh`, Patroni/etcd mTLS, E06-03). Doable when 09/12 unblock. |
| **E23-03** strict CSP (Web + Electron) | **blocked/toolchain** — needs the Vue build (nonces) + Electron `webSecurity` + Playwright header tests (Epic 07/08). The Caddy CSP *baseline* already ships (`deploy/*/reverse-proxy/Caddyfile` `(security_headers)`, E06-12). |
| **E23-10** threat model + pentest checklist + DPIA input | **blocked/dep** — the *complete* model needs the agent/BKU trust boundaries (Epic 09/10). A slice for the current system (login / presence / calls / integrations trust boundaries + DPIA data-flow list) is writeable now; the BKU-session section stays a stub. |
| **E23-11** agent-command fuzzing + door/DTMF review | **blocked/dep** — the agent-command deserialisation fuzzing needs E10-12/13. The **door/DTMF** half is doable now: E17-06 redaction is in place (`test_redaction.py`), the door-open flow has replay/duplicate guards (`test_siedle_door_open_flow.py`), and no DTMF plaintext reaches any sink. |
| **E23-12** cosign / SBOM verification at deploy | **blocked/dep** — needs `release.yml` producing signatures + SBOMs (E01-04 / E24-01, which is blocked/vendor on E12-01). `tools/rolling-update.sh` already refuses a non-digest `IMAGE`. |

## Epic 24 · Production Deployment — **in progress (2/8)**

| issue | status |
|---|---|
| E24-03 env / secret provisioning | **done** (#685) — `deploy/node/preflight.sh` + matrix |
| E24-05 backup/restore automation + tested restore | **done** (#686) — `restore-test.sh` + alerts |
| **E24-01** complete `release.yml` (SemVer+SHA, SBOM, cosign, GHCR, digests) | **blocked/vendor** — must cover *all* prod images incl. `cucm-cti-gateway` (E12-01). The api-only slice (build + SBOM + cosign + digest manifest for `bbz-api`) is doable once someone decides to ship a partial pipeline; deferred with E12. |
| **E24-02** production deployment manifests (2 + witness) | **blocked/dep** — E24-01. `deploy/node/` and `deploy/quorum/` composes exist and validate in CI; the digest-pinned, signed variant waits on E24-01. |
| **E24-04** rolling-update automation + pre-flight | **blocked/dep** — E24-01. `tools/rolling-update.sh` already has the health gates, the audit markers, the digest-only guard, and (E24-03) the per-node `preflight.sh`; what's missing is the signed-image verification step (E24-01/E23-12). |
| **E24-06** DR runbook (both servers / witness lost) | **doable now** — deps E24-05 ✓ + E06-11 ✓. Next up. |
| **E24-07** staging environment + smoke suite | **blocked/dep** — E24-02, plus E07-16 / E11-16 / E15-15 for the smoke content. |
| **E24-08** go-live checklist + acceptance plan + ops manual | **blocked/dep** — references practically every epic; a consolidation pass once 07–12 land. The individual runbooks (`docs/runbooks/*`) and checklists (`docs/mockup-parity-checklist.md`) already exist. |

---

## Open external dependencies (must not be invented)

`.ai/CURRENT_STATE.md` §"Open external dependencies" is authoritative. In short:
Cisco CUCM version + CTI config; Weytec API docs; Coda Video partner/API docs;
Siedle DTMF door profile; Entra ID OIDC params; LDAP/AD connection params. Each
integration is built strictly from documented vendor interfaces — the scaffolds
and unblocking checklists are in `docs/integrations/*` and `docs/auth/*`.
