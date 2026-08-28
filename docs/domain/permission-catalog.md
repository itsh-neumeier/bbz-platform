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

## Example scoped permission

`events.takeover` granted with scope `bbz` → user may take over events only
within their own BBZ.
