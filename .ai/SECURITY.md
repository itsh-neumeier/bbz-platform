# .ai/SECURITY.md

Target authentication:
- local users
- Entra ID OIDC
- LDAP/AD
- MFA

Security baseline:
- TLS
- Argon2id local passwords
- PKCE for OIDC
- secure cookies/tokens
- server-side RBAC
- audit
- secret management
- dependency/container scanning
- least privilege
- non-root containers where possible

No credentials in repo.


## Agent / remote control security
- Agents enroll with short-lived token and receive a unique device identity/certificate.
- No arbitrary shell/PowerShell/cmd execution endpoint.
- No arbitrary URL launch from operator input; only centrally allowlisted catalog entries.
- Remote logout/restart requires dedicated permission, explicit confirmation and audit.
- Commands contain command_id, nonce/sequence, expiry and are replay protected.
- Agent commands are routed through BBZ server authorization, not browser-to-agent direct trust.

## Door control security
- Door-open actions require a dedicated permission and complete audit trail.
- DTMF door codes are secrets/configuration values and must not be written in plaintext audit logs.
- Store secret values encrypted / via secret store; audit the action profile ID, not the code.
- Duplicate/replayed telephony events must never cause duplicate door-open actions.
