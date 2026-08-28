# bku-agent (PLACEHOLDER — no code)

Local service on the paired BKU workstation. **Not implemented in Phase 0**
(Phase 4). Design fixed by **ADR-0003** and `.ai/BKU_AGENT.md`.

- Enrolls against the BBZ platform; bound to one immutable `workplace_id` /
  `agent_id`; connects redundantly to SRV01/SRV02.
- **Strict typed allowlist only**: `get_status`, `get_session_state`,
  `launch/focus/close_catalog_app`, `logout_interactive_user`,
  `restart_workstation`, `ping`.
- **Never**: arbitrary shell / PowerShell / executable path / operator-supplied
  URL.
- Commands routed through BBZ server authorization + audit — no browser-to-agent
  direct trust. Each command: `command_id`, nonce/sequence, `expires_at`, replay
  protection.
- High-impact actions (logout/restart) require permission + explicit confirmation
  + audit.

Language (Go vs. Rust): **ADR-0009**.
