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
| 3 | login, provider choice (`local` only), session handling, logout | `features/auth/LoginView.vue`, `stores/session` | [#97](../../issues/97) (E07-02) | in-progress — login / TOTP step / session-expiry redirect / logout done + `e2e/auth.spec.ts`; force-password-change needs a backend self-service endpoint |
| 4 | TOTP challenge step, force-password-change | `LoginView` (TOTP step) | [#97](../../issues/97) | in-progress — TOTP step done; force-change is a stub until the backend endpoint |
| 5 | generic API client — command envelope, `X-Command-Id`, 409, correlation id echo | `lib/apiClient.ts` | [#99](../../issues/99) (E07-04) | in-progress — client + `ApiError`/`ConflictError`/`AuthExpiredError` + vitest done |
| 6 | event-stream client (SSE) + sync-status indicator, `after_seq` catch-up | `composables/useEventStream.ts`, `components/events/SyncStatus.vue` | [#101](../../issues/101) (E07-05) | in-progress — SSE client with catch-up + backoff reconnect + topbar indicator |
| 7 | event store / work queue (active queue, priority rank then age) | `/ereignisse`, `pages/QueuePage.vue`, `stores/events.ts` | [#103](../../issues/103) (E07-06) | in-progress — queue sorted by rank then age, live via the shell's SSE |
| 8 | accept / acknowledge / open / archive — **all four always visible** (§13.3), disabled by status | `components/events/EventActions.vue` (`all`) | [#103](../../issues/103), [#107](../../issues/107), [#716](../../issues/716) | done — the Ereignisspeicher shows all four per row (compact), each enabled only in its from-status, permission-gated, 409-aware |
| 9 | animated high / critical alerts + `prefers-reduced-motion` | `pages/WorkplacePage.vue` (row pulse), `PriorityPulse.vue`, `PriorityAlertBanner.vue` (topbar pill), `a11y/reducedMotion.ts` | [#105](../../issues/105) (E07-07), [#716](../../issues/716) | done — critical/high Ereignisspeicher rows pulse; the topbar priority pill pulses; the global `prefers-reduced-motion` rule stills all of it (colour stays) |
| 10 | event processing — description, status history, workflow/measures, notes, ownership — **inline on the Arbeitsplatz** (§13.3), also `/ereignisse/:id` | `components/events/EventProcessingPanel.vue`, thin `pages/EventDetailPage.vue` wrapper | [#107](../../issues/107) (E07-08), [#716](../../issues/716) | done — click a row → the panel opens below without leaving the page; the note form is gated on the real `events.postprocess` permission (was the non-existent `events.note`) |
| 11 | actions panel — workflow execution view (steps, decisions, progress) | `components/events/WorkflowRunPanel.vue` | [#109](../../issues/109) (E07-09) | in-progress — read view of the bound template + completed steps/decisions; act-on-step is a follow-up |
| 12 | full-event ownership — transfer, presence, take-over | `components/events/OwnershipBar.vue` | [#111](../../issues/111) (E07-10) | in-progress — assignee + "Übernehmen" (takeover) + presence select; assign-to-a-named-person deferred |
| 13 | archive view + postprocessing notes | `/archiv`, `pages/ArchivePage.vue`, shared `EventDetailPage` | [#113](../../issues/113) (E07-11) | in-progress — archived list + full history + post-processing notes on the detail |
| 14 | reactivation confirmation dialog (`confirm=true` + reason) | `components/events/ReactivateDialog.vue` | [#115](../../issues/115) (E07-12) | in-progress — native `<dialog>`, intent-token → confirm + mandatory reason → back to the active queue |
| 15 | global topbar alert for unaccepted high / critical events | `components/events/PriorityAlertBanner.vue` | [#117](../../issues/117) (E07-13) | in-progress — topbar banner off-queue, worst-priority colour, click → queue |
| 16 | i18n — DE locale complete + missing-key lint | `src/i18n/de.json`, `scripts/i18n-lint.mjs` | [#119](../../issues/119) (E07-14) | in-progress — `i18n:lint` script + CI step done; locale grows with each screen |
| 17 | accessibility baseline — keyboard paths, a11y-lint `error`, axe in E2E | `eslint.config.js` (`vuejs-accessibility` error), `e2e/a11y.spec.ts` | [#121](../../issues/121) (E07-15) | in-progress — a11y-lint at error level; axe-in-E2E is #123 |
| 18 | mandatory E2E — event lifecycle | `e2e/event-lifecycle.spec.ts` | [#123](../../issues/123) (E07-16) | todo |
| 19 | theme tokens — light / dark, `data-theme` | `src/theme/`, `composables/useTheme.ts` | [#125](../../issues/125) (E07-17), [#713](../../issues/713) | in-progress — rebuilt on **DB UX Design System v3** (ADR-0029): `--bbz-*` → `--db-*`, adaptive `light-dark()` dark mode via `data-mode` + `useTheme`, DB Screen Sans, DB brand red + logo. `docs/frontend/db-ux-design.md` |
| 20 | comms sidebar scaffold — tabs phone / call / phonebook / history | `CommsSidebar` tabs, `stores/calls.ts`, `lib/telephony.ts` | [#127](../../issues/127) (E07-18) | in-progress — the four tabs, keypad + line picker, waiting-call queue, active-call controls + documentation, mini phone-book, call history, line strip; `CommsSidebar.spec.ts` |
| 21 | graphical EPK editor (admin) | `/admin/workflows`, `WorkflowAdminPage.vue`, `lib/workflows.ts` | [#129](../../issues/129) (E07-19) | in-progress — structural editor: template + draft-version lifecycle, node/edge forms (event · function · connector), an auto-laid-out SVG preview, validate (E05-06 gate) + publish; drag-to-position on a canvas is a follow-up. `WorkflowAdminPage.spec.ts` |

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
| 40 | graphical EPK-style workflow editor | todo — UI is #129 (E07-19) |
| 41 | AND / OR / XOR connectors | backend-done (Epic 05 #75, #76) — editor #129 |
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
