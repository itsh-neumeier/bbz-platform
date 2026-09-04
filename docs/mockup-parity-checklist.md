# Mockup parity checklist

ADR-0013: *"Mockup parity … tracked explicitly (checklist in `docs/`), not
assumed."* Every feature from `.ai/FEATURES.md` (the functional mockup is the
product baseline) and MASTER_PROMPT §13 is listed here with the issue that
delivers its **UI**, and its status.

- **Mockup ref** — the `.ai/FEATURES.md` bullet / §13 topic. The mockup HTML
  itself lands under `docs/mockup/` (E01-02, open) — until then this column is
  the feature name.
- **Status** — one of: `todo` · `backend-done` (server API exists, UI pending)
  · `in-progress` · `done` · `n/a-here` (delivered by another epic's UI issue).
- A row is **done** only when its issue is merged **and** the Playwright E2E
  that exercises it is green.

The Web UI epic itself is **Epic 07** (issues #96–#129, `E07-01`…`E07-19`).
Feature areas whose UI lives in a later epic point at that epic.

## Core operator UI (Epic 07)

| # | Feature (mockup ref) | Target route / component | Issue | Status |
|---|---|---|---|---|
| 1 | app shell — logo cell / topbar / sidebar / content / version footer / resizable right column (comms + logbook) | `AppShell`, `LogoCell`, `TopBar`, `SidebarLeft`, `VersionBar`, `CommsSidebar`, `GlobalLog` | [#98](../../issues/98) (E07-03) | done — V10 grid (logo cell · shared topbar · sidebar · content · version footer · right column). Sidebar = workspace-status + nav with live badges + user card (theme + logout). Right column = comms over the cross-workplace `GlobalLog` (`GET /events/logbook`). `theme/mockup-surfaces.css` = the V10 card/tag/btn chrome on DB tokens. `docs/mockup/bbz-3sz-v10.html` committed (E01-02) |
| 2 | topbar: breadcrumb + page title, priority alert before the clock (§13.7), large clock w/ seconds, available lines, monitor-layout button; sidebar resize (drag + keyboard) | `TopBar`, `PriorityAlertBanner`, `CommsSidebar` handle | [#98](../../issues/98) | done — all V10 topbar elements; the animated priority pill sits before the clock; resize handle keyboard + drag |
| 3 | login, provider choice (`local` only), session handling, logout | `features/auth/LoginView.vue`, `stores/session` | [#97](../../issues/97) (E07-02) | done — login / TOTP step / session-expiry redirect / logout / **forced password change** (`POST /auth/password`, `/me.must_change_password`), all in `e2e/auth.spec.ts` |
| 4 | TOTP challenge step, force-password-change | `LoginView` (TOTP + change-password steps) | [#97](../../issues/97) | done — TOTP step + the forced new-password form (current proven, policy-checked, other sessions revoked); `e2e/auth.spec.ts` walks it |
| 5 | generic API client — command envelope, `X-Command-Id`, 409, correlation id echo | `lib/apiClient.ts` | [#99](../../issues/99) (E07-04) | in-progress — client + `ApiError`/`ConflictError`/`AuthExpiredError` + vitest done |
| 6 | event-stream client (SSE) + sync-status indicator, `after_seq` catch-up | `composables/useEventStream.ts`, `components/events/SyncStatus.vue` | [#101](../../issues/101) (E07-05) | done — SSE client with catch-up + backoff reconnect + the topbar indicator; `e2e/shell.spec.ts` asserts it reaches "verbunden" |
| 7 | event store / work queue (active, priority rank then age) → the **Ereignisspeicher** on the Arbeitsplatz | `pages/WorkplacePage.vue`, `stores/events.ts` | [#103](../../issues/103) (E07-06), [#716](../../issues/716) | done — the shared work queue is the top of the Arbeitsplatz (§13.3), rank then age, live via the shell SSE |
| 8 | accept / acknowledge / open / archive — **all four always visible** (§13.3), disabled by status | `components/events/EventActions.vue` (`all`) | [#103](../../issues/103), [#107](../../issues/107), [#716](../../issues/716) | done — the Ereignisspeicher shows all four per row (compact), each enabled only in its from-status, permission-gated, 409-aware |
| 9 | animated high / critical alerts + `prefers-reduced-motion` | `pages/WorkplacePage.vue` (row pulse), `PriorityPulse.vue`, `PriorityAlertBanner.vue` (topbar pill), `a11y/reducedMotion.ts` | [#105](../../issues/105) (E07-07), [#716](../../issues/716) | done — critical/high Ereignisspeicher rows pulse; the topbar priority pill pulses; the global `prefers-reduced-motion` rule stills all of it (colour stays). `e2e/shell.spec.ts` checks a critical row animates and that `reduce` shrinks it to nothing |
| 10 | event processing — description, status history, workflow/measures, notes, ownership — **inline on the Arbeitsplatz** (§13.3), also `/ereignisse/:id` | `components/events/EventProcessingPanel.vue`, thin `pages/EventDetailPage.vue` wrapper | [#107](../../issues/107) (E07-08), [#716](../../issues/716) | done — click a row → the panel opens below without leaving the page; the note form is gated on the real `events.postprocess` permission (was the non-existent `events.note`) |
| 11 | actions panel — workflow execution view (steps, decisions, progress) | `components/events/WorkflowRunPanel.vue` | [#109](../../issues/109) (E07-09) | done — per-step state + progress bar + "Schritt abschließen" on the active step (`workflows.execute`) + a button per branch for a pending XOR/OR split; 409-aware. `e2e/event-lifecycle.spec.ts` completes the step |
| 12 | full-event ownership — transfer, presence, take-over | `components/events/OwnershipBar.vue` | [#111](../../issues/111) (E07-10) | done — assignee + "Übernehmen" (takeover) + "Übergeben an" a named operator from `GET /events/assignable` + presence select. `e2e/event-lifecycle.spec.ts` takes over then hands back |
| 13 | archive + postprocessing notes — **folded into the Ereignisübersicht** (§13.6) | `pages/EventsPage.vue` ("Nur Archiv"), shared `EventProcessingPanel` | [#113](../../issues/113) (E07-11), [#717](../../issues/717) | done — one chronological list of all events (active + archived), `/archiv` redirects into it, `/archiv/:id` stays a deep link, post-processing notes + reactivation on the panel |
| 14 | reactivation confirmation dialog (`confirm=true` + reason) | `components/events/ReactivateDialog.vue` | [#115](../../issues/115) (E07-12) | done — native `<dialog>`, intent-token → confirm + mandatory reason → back to the active queue. `e2e/event-lifecycle.spec.ts` + `e2e/archive-lifecycle.spec.ts` reactivate an archived event |
| 15 | global topbar alert for unaccepted high / critical events | `components/events/PriorityAlertBanner.vue` | [#117](../../issues/117) (E07-13) | done — topbar banner off-queue (hidden on Arbeitsplatz/Ereignisse), worst-priority colour, click → the event; `e2e/shell.spec.ts` walks it |
| 16 | i18n — DE locale complete + missing-key lint | `src/i18n/de.json`, `scripts/i18n-lint.mjs` | [#119](../../issues/119) (E07-14) | in-progress — `i18n:lint` script + CI step done; locale grows with each screen |
| 17 | accessibility baseline — keyboard paths, a11y-lint `error`, axe in E2E | `eslint.config.js` (`vuejs-accessibility` error), `e2e/a11y.spec.ts` | [#121](../../issues/121) (E07-15) | done — `vuejs-accessibility` at error (blocking `frontend` CI); `e2e/a11y.spec.ts` runs `@axe-core/playwright` on Arbeitsplatz/Ereignisse/Wetterlage in **light + dark**, 0 critical/serious WCAG 2 A/AA. Fixed: shell-chrome muted text (emphasis 70→80) + the archived-row `opacity` that dragged every pair below AA |
| 18 | mandatory E2E — event lifecycle | `e2e/event-lifecycle.spec.ts` | [#123](../../issues/123) (E07-16) | done — the CI `e2e` job seeds a backend (`server/scripts/seed_e2e.py`), starts the API + Vite and runs Playwright: `event-lifecycle` walks §24 (accept → acknowledge → open → complete workflow step → takeover/assign → archive → archived detail → reactivate), plus `archive-lifecycle`, `auth`, `smoke`. `monitor-routing` stays `test.fixme` under E19-08/#408 |
| 19 | theme tokens — light / dark, `data-theme` | `src/theme/`, `composables/useTheme.ts` | [#125](../../issues/125) (E07-17), [#713](../../issues/713) | done — **DB UX Design System v3** (ADR-0029): `--bbz-*` → `--db-*`, adaptive `light-dark()` dark mode via `data-mode` + `useTheme`, DB Screen Sans, DB brand red + logo; `e2e/shell.spec.ts` cycles the toggle. `docs/frontend/db-ux-design.md` |
| 20 | comms sidebar scaffold — tabs phone / call / phonebook / history | `CommsSidebar` tabs, `stores/calls.ts`, `lib/telephony.ts` | [#127](../../issues/127) (E07-18) | in-progress — the four tabs, keypad + line picker, waiting-call queue, active-call controls + documentation, mini phone-book, call history, line strip; `CommsSidebar.spec.ts` |
| 21 | graphical EPK editor (admin) | `/admin/handlungsanweisungen` (under the `AdminPage` shell; `/admin/workflows` redirects, #725), `WorkflowAdminPage.vue`, `components/workflow/EpkCanvas.vue`, `lib/workflows.ts` | [#129](../../issues/129) (E07-19) | done — template + draft-version lifecycle, node/edge forms (event · function · connector), a real EPK canvas (hexagon / rounded-rect / connector circle + ∧/∨/⊕ glyph, vertical auto-layout `layoutRows`), pointer-drag **and** a full keyboard alternative for node positioning (`node.props.x/y`, no schema/migration/ADR change), validate (E05-06 gate) + publish. `WorkflowAdminPage.spec.ts`, `EpkCanvas.spec.ts`, `workflows.spec.ts`, `e2e/epk-editor.spec.ts` |
| 21b | Administration area — sub-nav + instance name (BBZ Nürnberg) | `pages/admin/AdminPage.vue` + `AdminInstancePage` / `AdminSystemPage` / `AdminPlaceholderPage`, `lib/admin.ts` | [#721](../../issues/721) (#718) | in-progress — `/admin` shell with a permission-gated sub-nav + guard; `/admin/instanz` edits the settings-store `instance` group (#720) and `/api/v1/meta` carries `instance_name` into the topbar / sidebar / login / title. All eight sub-sections are real pages (#722–#725, rows 21c–21f) |
| 21c | Administration — user management + per-role 2FA policy | `pages/admin/{AdminUsersPage,AdminMfaPolicyPage}.vue`, `lib/users.ts` | [#722](../../issues/722) (#718) | in-progress — `/admin/benutzer`: table + create local account + role checkboxes + activate/deactivate + admin password reset; `/admin/benutzer/mfa`: per-role "2FA erforderlich" + grace. `UserOut` gained `roles` + `providers`. Provider-specific/2FA-status columns are a follow-up |
| 21d | Administration — directory (LDAP) config + connection test | `pages/admin/AdminDirectoryPage.vue`, `lib/directory.ts`, `api/v1/admin_directory.py`, `LdapClient.probe` | [#723](../../issues/723) (#718) | in-progress — `/admin/verzeichnis`: connection fields (settings store) + `POST /admin/directory/test` (reachable/TLS/bind/sample) + group→role mappings + directory-sync trigger. `config_from_store` overlays the non-secret LDAP fields; bind password stays in the secret store |
| 21e | Administration — trigger rules + technical endpoints; EPK relocation | `pages/admin/{AdminTriggerRulesPage,AdminTechnicalEndpointsPage}.vue`, `lib/triggers.ts` | [#725](../../issues/725) (#718) | in-progress — `/admin/trigger-regeln` (list · versions · validate/publish/retire · simulate) + `/admin/technische-endpunkte` (CRUD); `/admin/workflows` → `/admin/handlungsanweisungen` redirect. JSON condition/action editing; a structured editor + a running-instances view are follow-ups |
| 21f | Administration — integrations (provider per domain + health) | `pages/admin/AdminIntegrationsPage.vue`, `api/v1/admin_integrations.py`, `lib/admin.ts` | [#724](../../issues/724) (#718) | in-progress — `/admin/integrationen`: `GET /admin/integrations` (registry × settings-store selection × health) → a card per domain with the adapter select (→ settings API), a health badge and a mock hint. Selection takes effect on restart (cached provider); wiring `active_*_provider()` through the store + a per-domain config form are follow-ups |

## Telephony & comms panel (Epic 11 / 14)

| # | Feature | Delivered by | Status |
|---|---|---|---|
| 22 | phone panel, keypad, incoming call queue | Epic 11 · #221 (`Komm-Sidebar-UI`) | in-progress — keypad + line picker + `POST /calls/dial`, waiting-call queue from `GET /calls/ringing` (comms sidebar Telefon tab) |
| 23 | contact priority blue / orange / red, call-priority animation | Epic 14 · #299, #301 | in-progress — contact priority blue/orange/red on the phone-book (`prio--low/medium/high` = `--bbz-prio-*` tokens); the call-priority pulse is the comms sidebar (#301) |
| 24 | mandatory call categorization, optional call free text | Epic 11 · #223 (`Anrufdokumentations-UI`) | in-progress — the Gespräch tab's documentation form (category radios + free text), `PUT /calls/{id}/documentation`; a "Dokumentation erforderlich" banner while the E11-10 hangup guard is open |
| 25 | phonebook (list, search, CRUD) | Epic 14 · #297 (`Telefonbuch-UI`) | in-progress — `/telefonbuch` `PhonebookPage.vue`: substring search (name/org/number) + quick-dial filter, create / edit fields / manage numbers / assign priority / soft-delete, all permission-gated; `PhonebookPage.spec.ts` |
| 26 | quick-dial dialog ("Kurzwahl öffnen" overlay) | Epic 11 · #225 | todo |
| 27 | contact ↔ call-history link (UI) | Epic 14 · #303 | todo |
| 28 | multiple waiting calls + priority sort | Epic 11 · #221 (UI) / #219 (backend) | in-progress — the waiting-call queue sorts by caller priority (high→low, unknown last) then wait time, priority-coloured with a reduced-motion-safe pulse |

## Technical triggers, Siedle, video, doorbell (Epic 15 / 16 / 17)

| # | Feature | Delivered by | Status |
|---|---|---|---|
| 29 | technical contacts / endpoints separate from the human phonebook | Epic 15 · #305 (schema), admin UI #322 | todo |
| 30 | telephone-number-based technical trigger rules, admin-configurable | Epic 15 · #307, #322 (`Trigger-Admin-API`/UI) | todo |
| 31 | BMA telephone trigger → exactly one event + attached workflow | Epic 15 · #329 (`BMA-Flow`) | todo |
| 32 | Siedle door-station workflow via telephony + DTMF | Epic 17 (`Siedle`) | todo |
| 33 | Coda Video camera action on doorbell ring | Epic 16 (`Coda Video`) | todo |
| 34 | bottom-right BBZ client doorbell popup | Epic 08 (desktop client) + Epic 16 | todo |
| 35 | Coda Video as inbound alarm source (panic / duress) → BBZ event | Epic 16 | todo |
| 36 | Coda alarm-source mapping to station / location / cameras / priority | Epic 16 | todo |
| 37 | Coda alarm → versioned EPK workflow mapping | Epic 16 | todo |
| 38 | exactly-once alarm ingestion, replay-safe failover | Epic 16 (builds on ADR-0011 inbox, done) | backend-done |
| 39 | camera-action failure must not block alarm / event creation | Epic 16 | todo |

## Workflow engine parity (Epic 05 — backend done)

| # | Feature | Status |
|---|---|---|
| 40 | graphical EPK-style workflow editor | done — #129 (E07-19), `e2e/epk-editor.spec.ts` |
| 41 | AND / OR / XOR connectors | backend-done (Epic 05 #75, #76); editor done (#129 — connector circle + ∧/∨/⊕ glyph) |
| 42 | versioned workflow templates, immutable running template version | backend-done (Epic 05 #74, #78) |

## Monitors, weather, BBZ-OS (Epic 18 / 19 + desktop)

| # | Feature | Delivered by | Status |
|---|---|---|---|
| 43 | DWD weather page | `pages/WeatherPage.vue` (`/wetterlage`) — E18-09 (#391) | in-progress — warnings + observations + radar timeline + "Ereignis erzeugen"; health badge; degrades on a `down`/`stale` feed |
| 44 | monitor routing dialog | `pages/MonitorPage.vue` (`/monitore`) — E19-08 (#408) | in-progress — 3×2 grid + large display, `<select>` keyboard alternative, standard-layout, user profiles |
| 45 | 6 workplace monitors + large display, standard layout | `pages/MonitorPage.vue` | in-progress — grid from the server catalog + `Standard-Layout` button (E19-04 reset) |
| 46 | BBZ-OS fixed on the lower-left monitor | `pages/MonitorPage.vue` shows `workplace4` locked + disabled; server-enforced (E19-03). Desktop display is Epic 08. | in-progress |

## BKU agent (Epic 10 — separate app)

| # | Feature | Delivered by | Status |
|---|---|---|---|
| 47 | dedicated BKU agent bound to each workplace | Epic 10 | todo |
| 48 | remotely visible BKU health / session state | Epic 10 + operator UI | todo |
| 49 | controlled BKU logout / restart with permission + confirmation + audit | Epic 10 | todo |
| 50 | centrally administered operational web-app / link catalog | Epic 10 · admin | todo |
| 51 | launch allowlisted apps (LeiDis / ARAMIS) in Chrome on the paired BKU client | Epic 10 | todo |

---

## Maintaining this file

- Each Epic-07 UI issue **must** flip its row(s) to `done` in the same PR and
  the reviewer checks the Playwright spec exists.
- A new mockup feature → add a row here in the PR that introduces it.
- `server/tests/test_parity_checklist.py` enforces: every `.ai/FEATURES.md`
  bullet is covered, every row has a valid status, every `#NNN` is a real
  issue reference, and the `E07-xx ↔ #issue` map is consistent.
