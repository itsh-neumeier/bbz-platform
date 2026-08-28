# ADR-0003: Dedicated BKU Agent Bound to BBZ Workplace

## Status
Accepted

## Context
The BBZ operator uses a dedicated BBZ client and an additional corporate BKU workstation. Operational web applications should be centrally available, and stale interactive BKU sessions at shift change must be controllable.

## Decision
Deploy a dedicated BKU Agent on the BKU workstation. It enrolls against the BBZ platform and is bound to one workplace. Commands are routed through the BBZ server authorization/audit layer.

The agent exposes a strict typed allowlist and no arbitrary remote command execution.

## Consequences
- central link/app catalog
- reliable workplace binding
- audited remote logout/restart
- reduced dependence on personal browser bookmarks
- additional endpoint software requiring enterprise deployment/update process
