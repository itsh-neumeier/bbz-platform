# Roadmap status — what is done, what is blocked, and why

Companion to `.ai/ROADMAP.md` and `.ai/CURRENT_STATE.md`. It exists so **no
roadmap issue is an undocumented gap**: every not-yet-merged issue has a status,
a blocker, and — where one exists — the slice that could still be done now.

_Last swept: 2026-09-03 (4th pass — the operator-UI build-out: PRs #702/#704/#705/#707; the closeable-issue list below)._

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
| 18 DWD weather | **done** — framework + 3 live adapters + fixtures; the `/wetterlage` UI (E18-09) shipped in #704 |
| 19 Weytec monitor routing | **done** — routing API + profiles + the fixed BBZ-OS rule; the `/monitore` dialog UI (E19-08) shipped in #704. `monitor_weytec` stays interface-only pending the Weytec API (`docs/integrations/weytec-monitor-pending.md`) |
| 20 Archive / Postprocessing | **backend-done** |
| 21 Enterprise Authentication | **backend-done** (E21-01..08) — OIDC/LDAP/MFA/WebAuthn/RBAC/linking; real IdP/dir params are an open dependency |
| 22 Monitoring / Observability | **done** (7/7) — tracing, metrics, log pipeline, health, integration-health, alerts, collector+dashboards |

---

## Backend-done, UI is Epic 07

These epics are fully functional on the server (schema, services, API, tests);
the operator UI is the only missing piece and every UI issue is an Epic-07 row.

| epic | UI issues waiting on Epic 07 |
|---|---|
| 11 Telephony Core | E11-13/14 **in progress** (comms sidebar, #707); E11-15 (Kurzwahl overlay), E11-16 (Playwright) open |
| 14 Contacts / Call Priorities | E14-07/08 **in progress** (phone-book, #705); E14-09 **in progress** (call-priority pulse, #707); E14-10 (history link) open |
| 15 Technical Trigger Engine | E15-14 (client-popup UI) open |
| 16 Coda Video | E16-12 (camera view) open; alarm/camera transport is `mock: true` pending Coda docs (blocked/vendor) |

(Epic 13 SIP is 5/8 — the ARI adapter is built (E13-03..06, PRs #777–#780);
E13-07 config UI + E13-08 lab-PBX tests remain. See its section below.)

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

## Epic 07 · Web UI / PrimeVue — **in progress (~11/19 done, 7 in progress, 1 todo)**

The Vue toolchain runs in a `node:22-alpine` container (E01-06 made the
`frontend` CI job blocking). PRs #701 / #702 / #704 / #705 / #707 / #708 built
the operator UI on the app shell. A row reaches **done** only once a Playwright
E2E that exercises it runs in CI — that job is #123, still open — so most rows
sit at "in progress · feature complete".

| issue | status |
|---|---|
| E07-01 #96 mockup-parity checklist | **done** |
| E07-02 #97 auth UI (login · TOTP · session · logout) | **in progress** — login + TOTP step + session-expiry redirect + logout + `e2e/auth.spec.ts`; force-password-change needs a backend `POST /auth/password` (does not exist) |
| E07-03 #98 app shell (topbar · line status · resize) | **in progress** — `AppShell` (one SSE feed → events **and** calls stores), `TopBar` (clock · theme toggle · logout), `SidebarLeft`, resizable `CommsSidebar` |
| E07-04 #99 generic API client | **done** — `lib/apiClient.ts`: command envelope, real-UUID `X-Command-Id`, `409 → ConflictError`, `401 → AuthExpiredError`, CSRF echo + `apiClient.spec.ts` |
| E07-05 #101 SSE client + sync indicator | **done** — `useEventStream` (after_seq catch-up, backoff reconnect) + `SyncStatus` |
| E07-06 #103 work queue | **done** — `/ereignisse` `QueuePage` + `stores/events` (rank then age, live) |
| E07-07 #105 priority animation | **done** — `PriorityPulse` + `useReducedMotion` (still dot under reduced motion) |
| E07-08 #107 event detail | **done** — `/ereignisse/:id` `EventDetailPage` (description · status history · work notes) |
| E07-09 #109 workflow view | **in progress** — `WorkflowRunPanel` read view; act-on-step is a follow-up |
| E07-10 #111 ownership UI | **in progress** — `OwnershipBar` (assignee + takeover + presence); assign-to-a-person deferred |
| E07-11 #113 archive view | **done** — `/archiv` `ArchivePage` + shared detail page; `e2e/archive-lifecycle.spec.ts` un-`fixme`d |
| E07-12 #115 reactivation dialog | **done** — `ReactivateDialog` (intent-token → confirm + mandatory reason) |
| E07-13 #117 priority-alert banner | **done** — `PriorityAlertBanner` (off-queue, worst-priority colour) |
| E07-14 #119 i18n + missing-key lint | **done** — `scripts/i18n-lint.mjs` + CI step |
| E07-15 #121 a11y baseline | **in progress** — `vuejs-accessibility` at error level; axe-in-E2E is #123 |
| E07-16 #123 mandatory E2E | **todo** — the specs exist and are un-`fixme`d; no Playwright CI job runs them yet |
| E07-17 #125 theme tokens | **done** — `theme/tokens.css` + `useTheme` (system/light/dark, persisted) + toggle |
| E07-18 #127 comms sidebar | **in progress** — keypad + line picker + waiting-call queue, active-call controls + mandatory documentation, mini phone-book, call history, line strip; `CommsSidebar.spec.ts` |
| E07-19 #129 graphical EPK editor | **in progress** — `/admin/workflows` `WorkflowAdminPage`: template + draft-version lifecycle, node/edge forms, an auto-laid-out SVG preview, validate + publish; canvas drag-to-position is a follow-up |

**Also shipped, outside the E07 issue list** (the owning epic's UI issue):
`/wetterlage` (E18-09, #391), `/monitore` (E19-08, #408), `/telefonbuch`
(E14-07/08, #297/#299).

Still gated: **#14** (deliberate frontend dependency major-upgrade pass).

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

## Epic 13 · SIP Provider — **5/8 + ADR-0023/0033 (`Accepted`)**

- **E13-01 done**: `integrations/telephony_sip/` scaffold — manifest,
  `config_schema.json`, and a `SipTelephonyProvider` that satisfies the whole
  `TelephonyProvider` protocol.
- **E13-02 — decision done, ADR-0023 `Accepted`**: **Asterisk via ARI** (REST +
  WebSocket + JSON, the transport the codebase already speaks; the Stasis
  channel model fits the provider verbs; ARI events map straight onto
  `inbound_signal.v1`). FreeSWITCH ESL stays the documented fallback in
  `config_schema.json`.
- **ADR-0033 `Accepted`** (#273, PR #777): the SIP gateway config is DB-backed
  and UI-managed; the ARI password is Fernet-encrypted at rest (the
  `door_action_profiles` pattern). Scoped exception to ADR-0031.
- **E13-03..06 — adapter code done, issues open pending E13-08** (PRs
  #777–#780): the ARI transport (`ari.py` — REST + reconnecting event WS),
  event mapping (`events.py`) + the `telephony-events` cluster singleton that
  drains the pump (also closes the E11-05 real-provider gap), call control
  (idempotent verbs over a `source_call_id → channel` map) and `send_dtmf`
  (redaction-safe, idempotent). Covered by `httpx.MockTransport` unit tests;
  #273/#275/#277/#279 stay open until E13-08's lab-Asterisk integration tests
  exercise them (their AC: "Integration gegen Test-Gateway").
- **E13-07 next**: the DB config tables + `bbz_core.infra.sip_secrets` + the
  `/api/v1/admin/telephony/sip` API + the `/admin/telefonie` UI (ADR-0033), and
  wiring `active_telephony_provider()` to build the ARI client from the DB.
- **E13-08 next**: a `sip`-profile Asterisk container + `ari.conf`/dialplan +
  integration scenarios, run nightly. E13-06 (the real `send_dtmf` transport)
  is also the missing piece for Epic 17's real door opening.

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
| bulk-close the completed-but-open issues | list + one-liner in the next section; the agent's bulk `gh issue close` is denied by the auto-mode classifier |

## Completed issues still open on the tracker

These issues are **done on `main`** (merged + tested — see the per-epic sections
of `.ai/CURRENT_STATE.md`) but were never closed. The agent's bulk
`gh issue close` is blocked by the auto-mode classifier. Close them in one pass:

```sh
for n in 59 92 145 165 167 191 197 199 201 203 205 207 209 211 213 215 217 219 \
  269 285 287 289 291 293 295 297 299 305 307 309 311 313 315 317 319 320 322 \
  324 326 329 333 335 337 339 341 343 345 347 349 351 353 355 359 361 363 365 \
  367 369 371 373 375 377 379 381 383 385 387 389 391 393 395 397 398 400 402 \
  404 406 408 410 412 414 416 418 420 422 424 426 429; do
  gh issue close "$n" --reason completed --comment \
    "Backend/scaffold complete and merged to \`main\` — see .ai/CURRENT_STATE.md and docs/roadmap-status.md. Any UI / Playwright follow-up is tracked under Epic 07 and #123."
done
```

That is **88 issues**: Epic 04 (#59), 06 (#92), 09-scaffold (#145),
10-schema/seed (#165/#167/#191), 11 backend (#197–#219), 13-scaffold (#269),
14 backend + phone-book (#285–#299), 15 backend (#305–#333), 16 backend
(#335–#359), 17 (#361–#373), 18 incl. `/wetterlage` (#375–#393), 19 incl.
`/monitore` (#395–#412), 20 (#414–#429).

**Keep open**: every E07 issue (#97–#129), E08 (#131–#143), E09-02..10
(#147–#163), E10-03..13/15/16 (#169–#195), E11-15/16 (#225/#227), E12 (all,
#229–#267), E13-02..08 (#271–#283), E14-09/10 (#301/#303), E15-14 (#331),
E16-12 (#357), E23 (#462/#464/#478/#480/#482), E24 (#484/#486/#490/#496/#498),
plus #14 and #18.
