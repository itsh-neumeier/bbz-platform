# BKU Agent – Workplace Integration

## Purpose

Each BBZ workplace may have a separate corporate BKU workstation. A dedicated `bku-agent` runs on that BKU client and is permanently bound to the corresponding BBZ workplace.

The goal is to make recurrent daily-operation applications centrally available and to provide controlled lifecycle/session actions without requiring every operator to maintain personal bookmarks.

## Components

- BBZ Electron/Chromium client
- BBZ client agent
- BKU workstation
- BKU Agent Windows service
- optional user-session helper process for launching visible Chrome windows
- BBZ server command/event layer

## Trust model

The BBZ browser/client must NOT directly execute remote OS commands on the BKU client.

Flow:

`BBZ Client -> BBZ API (authorize/audit) -> Agent Command Bus -> paired BKU Agent -> result event`

The agent connects redundantly to BBZ-SRV01/SRV02 and continues through the surviving server.

## Enrollment / binding

Default is one BKU Agent per BBZ workplace.

1. Admin creates/enrolls the BKU client for a workplace.
2. Server issues a short-lived enrollment token.
3. Agent generates device key material and enrolls.
4. Server assigns immutable `agent_id` and `workplace_id`.
5. Normal operation uses device identity/certificate; never reuse enrollment token.

## Required commands

Provider-independent logical commands:

- `get_status()`
- `get_session_state()`
- `launch_catalog_app(app_id)`
- `focus_catalog_app(app_id)`
- `close_catalog_app(app_id)` where allowed
- `logout_interactive_user()`
- `restart_workstation()`
- `ping()`

Optional later:
- `lock_workstation()`
- `collect_diagnostics()`

Never implement:
- arbitrary shell command
- arbitrary PowerShell
- arbitrary executable path
- arbitrary URL supplied by normal operator

## Application / Link Catalog

Server-managed catalog object:

- app_id
- name
- description
- icon
- url
- browser_profile
- launch_mode (`window`, `app_window`, `tab`)
- allowed_roles/scopes
- enabled
- sort_order
- optional workplace/site scope
- optional target monitor hint
- version

Example entry:

- Name: `LeiDis (ARAMIS)`
- Target: BKU
- Launch: Chrome window

Operators receive centrally maintained buttons in the BBZ client. They do not manage local bookmarks.

## Shift change

The BBZ client shows paired BKU state. If an interactive BKU user/session from the previous shift is still present, authorized staff can choose:

- `BKU Benutzer abmelden`
- `BKU Client neu starten`

Both are high-impact commands and require:

- permission
- explicit confirmation dialog
- reason/shift context if configured
- audit entry

## Suggested permissions

- `bku.status.view`
- `bku.apps.launch`
- `bku.apps.close`
- `bku.session.logout`
- `bku.device.restart`
- `bku.catalog.view`
- `bku.catalog.manage`
- `bku.agent.manage`

## Reliability

Each command has:

- command_id
- workplace_id
- agent_id
- issued_at
- expires_at
- requested_by
- expected agent generation/session where relevant

Commands are idempotent where possible and replay-protected.
