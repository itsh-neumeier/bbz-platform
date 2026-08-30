# Permission & scope catalog (seed)

Seeded from MASTER_PROMPT §12 / §28.3 / §30.1. RBAC is fully dynamic (users,
groups, roles, permissions, scopes, optional conditions). Phase 1 turns this into
the enforced model. **Enforcement is server-side, always.**

## Scopes

`global` · `region` · `bbz` · `workplace` · `own_events` · `assigned_events`

## Permissions

| Area | Permissions |
|---|---|
| Events | `events.view` `events.create` `events.accept` `events.acknowledge` `events.open` `events.edit` `events.assign` `events.takeover` `events.close` `events.archive` `events.reactivate` `events.postprocess` `events.export` |
| Workflows | `workflows.view` `workflows.execute` `workflows.override` `workflows.manage_templates` |
| Calls | `calls.view` `calls.answer` `calls.dial` `calls.hangup` `calls.hold` `calls.transfer` `calls.document` `calls.view_history` |
| Contacts | `contacts.view` `contacts.create` `contacts.edit` `contacts.delete` `contacts.assign_priority` |
| Monitor | `monitor.view` `monitor.route` `monitor.reset_standard` `monitor.manage_profiles` |
| Weather | `weather.view` `weather.create_event` |
| Users/Roles | `users.view` `users.manage` `roles.view` `roles.manage` `permissions.manage` |
| Integrations | `integrations.view` `integrations.configure` `integrations.enable_disable` `integrations.diagnostics` |
| System | `system.audit.view` `system.cluster.view` `system.cluster.manage` `system.settings.manage` |
| BKU | `bku.status.view` `bku.apps.launch` `bku.apps.close` `bku.session.logout` `bku.device.restart` `bku.catalog.view` `bku.catalog.manage` `bku.agent.manage` |
| Door / technical | `door.view` `door.answer` `door.open` `door.configure` `technical_endpoints.view` `technical_endpoints.manage` |

## BKU least-privilege defaults (E10-14)

The eight `bku.*` keys are seeded by migration 0008 (generic catalog + built-in
roles). The default role grants keep the high-impact actions with the senior
roles:

| Role | BKU grants |
|---|---|
| Administrator | all eight |
| Sichtleiter | all eight |
| Disponent | `bku.status.view`, `bku.apps.launch`, `bku.apps.close` only |
| Nachbearbeitung | none |
| Nur Lesen | at most `bku.status.view`, `bku.catalog.view` |

`bku.session.logout` and `bku.device.restart` (end a user's session / reboot a
workstation) are **Administrator / Sichtleiter only**. Enforced by
`server/tests/test_bku_permissions_seed.py`.

## Example scoped permission

`events.takeover` granted with scope `bbz` → user may take over events only
within their own BBZ.
