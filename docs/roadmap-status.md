# Roadmap status — what is done, what is blocked, and why

Companion to `.ai/ROADMAP.md` and `.ai/CURRENT_STATE.md`. It exists so **no
roadmap issue is an undocumented gap**: every not-yet-merged issue has a status,
a blocker, and — where one exists — the slice that could still be done now.

_Last swept: 2026-09-02 (3rd pass — Epic 01 leftovers + ADR-0023)._

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
| 01 Repository Foundation | **6/7** — E01-01/03/04/05/06/07 done; only E01-02 blocked (client-supplied mockup files) |
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
| 14 Contacts / Call Priorities | E14-07..10 (UI) |
| 15 Technical Trigger Engine | E15-14 (UI) |
| 16 Coda Video | E16-xx UI; alarm/camera transport is `mock: true` pending Coda docs (blocked/vendor) |

(Epic 13 SIP is **not** backend-done — 1/8 + ADR-0023; see its section below.)

---

## Epic 01 · Repository Foundation — **6/7**

| issue | status |
|---|---|
| E01-01 ADRs 0007–0018 → Accepted | **done** |
| E01-03 secret-store decision (ADR-0019) | **done** |
| E01-04 `release.yml` (image build, SBOM, cosign, GHCR) | **done** (#692) — `bbz-api` complete: tag `v*` → semver+SHA tags, Syft SPDX SBOM, cosign keyless sign + attest, Trivy gate, GitHub Release; `cosign verify` in-job. New `actionlint` CI job. `bbz-web` is a one-line matrix add once `apps/web` has a Dockerfile (Epic 07). Maintainer still owes the tag-push dry-run (`docs/deploy/releases.md`). |
| E01-05 branch-protection settings | **done** (#693) — `docs/repo-settings.md`: the check-runs by exact name + a `gh api` recipe + `v*` tag protection. **A maintainer still runs the `gh api` call** — modifying repo settings is outside what the agent may do. |
| E01-06 frontend-CI hardening | **done** (#699) — `apps/web/package-lock.json` regenerated (in a `node:22-alpine` container) + committed; CI `frontend` job is `npm ci` and **blocking** (`continue-on-error` removed); `docs/DEV_SETUP.md` names Node 22. |
| E01-07 coverage + import-boundary gates | **done** (#694) — 7 `import-linter` contracts (one per ADR-0008 layer) + `tools/coverage_gates.py` (per-layer 90 % targets, report-only/ratcheted) + `docs/CONVENTIONS.md` "Quality gates". |
| **E01-02** commit the functional HTML mockup | **blocked/vendor** — the mockup source files are an explicit external dependency (client-supplied) per the issue. `docs/mockup-parity-checklist.md` (the other AC) already exists. |

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

All 7 issues need Node + Electron. `E08-07` (ADR-0022, load strategy:
server-build vs bundle) is an open decision — **not drafted**, because it
depends on the unbuilt E08-01 Electron scaffold and the choice interacts with
app structure that doesn't exist yet. The lean is *bundle* (offline robustness
for a critical-infra kiosk). Nothing shippable here without an Electron build
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

## Epic 13 · SIP Provider — **1/8 + ADR-0023 (`Accepted`)**

- **E13-01 done**: `integrations/telephony_sip/` scaffold — manifest,
  `config_schema.json`, and a `SipTelephonyProvider` that satisfies the whole
  `TelephonyProvider` protocol with safe stubs (`SipNotConfiguredError` on every
  control verb until E13-03+).
- **E13-02 — decision done, ADR-0023 `Accepted`**: **Asterisk via ARI** (REST +
  WebSocket + JSON, the transport the codebase already speaks; the Stasis
  channel model fits the provider verbs; ARI events map straight onto
  `inbound_signal.v1`). FreeSWITCH ESL stays the documented fallback in
  `config_schema.json`.
- **E13-02 deployment half + E13-03..08 blocked/toolchain**: the `asterisk`
  compose container + `ari.conf`/dialplan + SIPp smoke test, then the adapter,
  event mapping, call control, DTMF, secrets and PBX integration tests — all
  need a SIP stack / containerized test PBX in the environment. E13-06 (the real
  `send_dtmf` transport) is also the missing piece for Epic 17's real door
  opening.

---

## Epic 23 · Security Hardening — **in progress (7/12 + E23-10/E23-11 partial)**

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
| **E23-10** threat model + pentest checklist + DPIA input | **partial — done** (#688) for the current system: `docs/security/{threat-model,pentest-checklist,dpia-input}.md` cover every trust boundary + data flow that exists today. The BKU-agent boundary (#5) and BKU-session data flows stay stubbed pending Epic 09/10; retention values in the DPIA input must be set before go-live. |
| **E23-11** agent-command fuzzing + door/DTMF review | **partial — door/DTMF half already covered**, no code needed: `test_siedle_audit_no_dtmf.py` asserts no DTMF plaintext in any audit sink, E17-06 redaction (`test_redaction.py`), replay/duplicate guards (`test_siedle_door_open_flow.py`). The agent-command deserialisation fuzzing half is **blocked/dep** on E10-12/13 (Go agent). |
| **E23-12** cosign / SBOM verification at deploy | **blocked/dep** — needs `release.yml` producing signatures + SBOMs (E01-04 / E24-01, which is blocked/vendor on E12-01). `tools/rolling-update.sh` already refuses a non-digest `IMAGE`. |

## Epic 24 · Production Deployment — **in progress (3/8)**

| issue | status |
|---|---|
| E24-03 env / secret provisioning | **done** (#685) — `deploy/node/preflight.sh` + matrix |
| E24-05 backup/restore automation + tested restore | **done** (#686) — `restore-test.sh` + alerts |
| E24-06 DR runbook (both servers / witness lost) | **done** (#689) — `docs/runbooks/disaster-recovery.md` scenario ladder § A–E + RTO targets; staging drill per scenario still owed |
| **E24-01** complete `release.yml` (SemVer+SHA, SBOM, cosign, GHCR, digests) | **blocked/vendor for the last mile** — the `bbz-api` pipeline shipped as **E01-04** (#692). E24-01 = extend the `matrix.include` to `bbz-web` (needs the `apps/web` Dockerfile — Epic 07) and `cucm-cti-gateway` (E12-01), and wire deploy-time `cosign verify` (E23-12). |
| **E24-02** production deployment manifests (2 + witness) | **blocked/dep** — E24-01. `deploy/node/` and `deploy/quorum/` composes exist and validate in CI; the digest-pinned, signed variant waits on E24-01. |
| **E24-04** rolling-update automation + pre-flight | **blocked/dep** — E24-01. `tools/rolling-update.sh` already has the health gates, the audit markers, the digest-only guard, and (E24-03) the per-node `preflight.sh`; what's missing is the signed-image verification step (E24-01/E23-12). |
| **E24-07** staging environment + smoke suite | **blocked/dep** — E24-02, plus E07-16 / E11-16 / E15-15 for the smoke content. |
| **E24-08** go-live checklist + acceptance plan + ops manual | **blocked/dep** — references practically every epic; a consolidation pass once 07–12 land. The individual runbooks (`docs/runbooks/*`) and checklists (`docs/mockup-parity-checklist.md`) already exist. |

---

## Open external dependencies (must not be invented)

`.ai/CURRENT_STATE.md` §"Open external dependencies" is authoritative. In short:
Cisco CUCM version + CTI config; Weytec API docs; Coda Video partner/API docs;
Siedle DTMF door profile; Entra ID OIDC params; LDAP/AD connection params. Each
integration is built strictly from documented vendor interfaces — the scaffolds
and unblocking checklists are in `docs/integrations/*` and `docs/auth/*`.

## Waiting on a maintainer (not a code task)

| action | why |
|---|---|
| run the branch-protection `gh api` call | the recipe is in `docs/repo-settings.md` (checks list includes `frontend` now); nothing enforces required checks / reviews until it's run — the agent is not permitted to modify repo settings |
| tag-push dry-run of `release.yml` | E01-04's remaining AC — push a real `vX.Y.Z`, `cosign verify` the digest, clean up (`docs/deploy/releases.md`) |
| supply the functional HTML mockup files | unblocks E01-02 (`docs/mockup/`) and is the frontend test baseline for Epic 07 |
| fix GitHub Actions billing, then re-privatise the repo | the repo was made **public** to work around a spending-limit block and is **still public**; CI currently works *because* of that |
