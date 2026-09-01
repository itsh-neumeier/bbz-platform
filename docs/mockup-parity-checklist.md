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
| 1 | app shell — sidebar / topbar / content / resizable comms sidebar | `App.vue`, `AppShell`, `CommSidebar` | [#98](../../issues/98) (E07-03) | backend-done |
| 2 | topbar clock, line status, sidebar resize (drag + keyboard) | `Topbar`, `LineStatus`, `useSidebarResize` | [#98](../../issues/98) | backend-done |
| 3 | login, provider choice (`local` only), session handling, logout | `/login`, `LoginView`, `useSession` | [#97](../../issues/97) (E07-02) | backend-done |
| 4 | TOTP challenge step, force-password-change | `TotpChallenge`, `ForcePasswordChange` | [#97](../../issues/97) | backend-done |
| 5 | generic API client — command envelope, `X-Command-Id`, 409, correlation id echo | `lib/apiClient.ts` | [#99](../../issues/99) (E07-04) | backend-done |
| 6 | event-stream client (SSE) + sync-status indicator, `after_seq` catch-up | `useEventStream`, `SyncStatus` | [#101](../../issues/101) (E07-05) | backend-done |
| 7 | event store / work queue (active queue, priority rank then age) | `/queue`, `WorkQueue`, `useEvents` | [#103](../../issues/103) (E07-06) | backend-done |
| 8 | accept / acknowledge / open / archive from the queue + detail | `EventActions` | [#103](../../issues/103), [#107](../../issues/107) | backend-done |
| 9 | animated high / critical alerts + `prefers-reduced-motion` | `PriorityPulse`, `useReducedMotion` | [#105](../../issues/105) (E07-07) | backend-done |
| 10 | event detail / message panel (description, status history, notes, assignee) | `/events/:id`, `EventDetail` | [#107](../../issues/107) (E07-08) | backend-done |
| 11 | actions panel — workflow execution view (steps, decisions, progress) | `WorkflowRunPanel` | [#109](../../issues/109) (E07-09) | backend-done |
| 12 | full-event ownership — transfer, presence, take-over | `OwnershipBar`, `TakeoverDialog`, `PresenceBadge` | [#111](../../issues/111) (E07-10) | backend-done |
| 13 | archive view + postprocessing notes | `/archive`, `ArchiveList`, `PostprocessNotes` | [#113](../../issues/113) (E07-11) | backend-done |
| 14 | reactivation confirmation dialog (`confirm=true` + reason) | `ReactivateDialog` | [#115](../../issues/115) (E07-12) | backend-done |
| 15 | global topbar alert for unaccepted high / critical events | `PriorityAlertBanner` | [#117](../../issues/117) (E07-13) | backend-done |
| 16 | i18n — DE locale complete + missing-key lint | `locales/de.json`, `scripts/i18n-lint` | [#119](../../issues/119) (E07-14) | todo |
| 17 | accessibility baseline — keyboard paths, a11y-lint `error`, axe in E2E | eslint config, `e2e/a11y.spec.ts` | [#121](../../issues/121) (E07-15) | todo |
| 18 | mandatory E2E — event lifecycle | `e2e/event-lifecycle.spec.ts` | [#123](../../issues/123) (E07-16) | todo |
| 19 | theme tokens — light / dark, `data-theme` | `assets/tokens.css`, `useTheme` | [#125](../../issues/125) (E07-17) | todo |
| 20 | comms sidebar scaffold — tabs phone / call / phonebook / history | `CommSidebar` tabs | [#127](../../issues/127) (E07-18) | todo |
| 21 | graphical EPK editor (admin) | `/admin/workflows/:id/edit`, `EpkEditor` | [#129](../../issues/129) (E07-19) | todo |

## Telephony & comms panel (Epic 11 / 14)

| # | Feature | Delivered by | Status |
|---|---|---|---|
| 22 | phone panel, keypad, incoming call queue | Epic 11 · #221 (`Komm-Sidebar-UI`) | todo |
| 23 | contact priority blue / orange / red, call-priority animation | Epic 14 · #299, #301 | todo |
| 24 | mandatory call categorization, optional call free text | Epic 11 · #223 (`Anrufdokumentations-UI`) | todo |
| 25 | phonebook (list, search, CRUD) | Epic 14 · #297 (`Telefonbuch-UI`) | todo |
| 26 | quick-dial dialog ("Kurzwahl öffnen" overlay) | Epic 11 · #225 | todo |
| 27 | contact ↔ call-history link (UI) | Epic 14 · #303 | todo |
| 28 | multiple waiting calls + priority sort | Epic 11 · #221 (UI) / #219 (backend) | todo |

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
| 43 | DWD weather page | Epic 18 · `DWD Weather` | todo |
| 44 | monitor routing dialog | Epic 19 · `Weytec Monitor Routing` | backend-done (E19-04/05 API; dialog UI is E19-08 → Epic 07) |
| 45 | 6 workplace monitors + large display, standard layout | Epic 19 | backend-done (E19-02 catalog + standard layout, E19-04 reset) |
| 46 | BBZ-OS fixed on the lower-left monitor | Epic 08 (BBZ Desktop Client) | backend-done (E19-03 server-enforced; desktop display is Epic 08) |

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
