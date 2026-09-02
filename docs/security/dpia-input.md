# DPIA input — personal-data flows

Roadmap **E23-10** (partial). This is **input for** a Data Protection Impact
Assessment, not the assessment itself — the legal evaluation is the customer's
data-protection officer's job (co-determination / *Mitbestimmung* applies to the
BKU-session monitoring and remote logout/restart features).

It lists every flow of data that can be linked to a natural person, with the
purpose, retention, and the data-subject rights touchpoint.

## Categories of data subject

- **Operators / dispatchers** — the BBZ platform users.
- **Callers** — people who phone the Leitstelle (name only if in the phone book).
- **Workstation users** (BKU) — whoever is logged in at a kiosk. *(pending Epic 10)*

## Data-flow register

| # | data | subject | source → store | purpose | retention | legal basis (indicative) | subject rights |
|---|---|---|---|---|---|---|---|
| 1 | **login events** — username, provider, source IP, user-agent, success/failure, MFA outcome | operator | `/auth/*` → `audit_events` | security monitoring, incident investigation, lockout | audit retention (config `KEEP_DAYS`; set to the legal requirement) | legitimate interest / legal obligation (IT security) | access, rectification of the *account*, not the log line (append-only) |
| 2 | **sessions** — device, user-agent, issued/last-seen/revoked timestamps | operator | `/auth/login` → `sessions` | keep the operator signed in; revoke on directory off-boarding | until expiry or revocation; row kept for audit | contract (employment) | access; erasure = deactivate the account (sessions revoked) |
| 3 | **presence** — availability state, workstation, live/offline | operator | `PUT /presence` → `presence` | show the roster so calls/events route to an available dispatcher | current value only (overwritten); the *change* is not separately logged | contract (employment) | access via `/presence` |
| 4 | **role / permission assignments**, MFA enrolment, WebAuthn credentials, linked identities | operator | RBAC/MFA admin + self-service → `user_roles` / `local_totp` / `webauthn_credentials` / `auth_identities` | authorisation; second factor | while employed; changes audited (critical actions) | contract / legal obligation | access; the audit trail of changes is append-only |
| 5 | **calls** — line, direction, caller number, timestamps, state | caller + operator | telephony provider → inbox → `calls` / `call_participants` | Leitstelle operations — connect, document, prioritise | operational + the legal call-documentation requirement | legal obligation (Leitstellen operation) | caller: information on request; the number is the minimum needed |
| 6 | **caller resolution** — number → phone-book contact + priority | caller | `caller_resolution` against `contacts` | show the dispatcher who is calling and how urgent | phone book is master data, maintained by operators | legitimate interest (operations) | the phone book is subject to the normal contact-data rights |
| 7 | **call documentation** — free-text notes, category, the documenting operator | caller + operator | `PUT /calls/{id}/documentation` → `call_documentation` | mandatory call record | legal call-documentation retention | legal obligation | access on request; corrections via a new note (records are not overwritten) |
| 8 | **events & notes** — title/description, assignee, takeover history, post-processing notes, the acting operator | operators (+ any person named in free text) | `/events/*` → `events` / `event_notes` / `domain_events` | incident management, handover, audit | operational + archive retention; `domain_events` is append-only | legal obligation (Leitstelle) | free-text may name third parties — minimise; access on request |
| 9 | **audit trail** — actor, action, target, before/after, correlation id, node | operator | every critical write → `audit_events` (hash-chained) | tamper-evident record of who did what | the audit retention period (set it explicitly) | legal obligation | append-only by design; a subject-access request is served *from* it, it is not edited |
| 10 | **traces / logs** — `user_id`, `correlation_id`, `trace_id`, route, status | operator | request path → stdout (+ optional file sink) | debugging, latency/error analysis | short — no log store is operated by the platform; a sidecar ships them per the operator's retention | legitimate interest | never contains a token/password/DTMF; `user_id` is a UUID |
| 11 | **BKU session monitoring** — who is logged in at a workstation, session state | workstation user | *(Epic 10 — not built)* | shift-change awareness, remote logout/restart | *(to be defined with co-determination)* | *(co-determination — Betriebsrat)* | *(pending)* |
| 12 | **remote logout / restart** — the operator who triggered it, the target workstation, confirmation | operator + workstation user | *(Epic 10)* → `bku_agent_commands` + audit | operational recovery of a stuck kiosk | audit retention | *(co-determination)* | *(pending)* |

## Minimisation already in place

- Provider events carry **only normalised handles** — no vendor object ids, no
  raw provider payloads persisted beyond the inbox.
- The redaction layer (E17-06) guarantees no secret (token, password, DTMF,
  recovery code) reaches a log, trace, or audit row.
- `user_id` in logs/traces is an opaque UUID, not a name.
- Free-text fields (event/call notes) are the main third-party exposure — the
  operator UI (Epic 07) should carry a data-minimisation hint.

## Retention — action required

`deploy/backup/common.sh` `KEEP_DAYS` / `KEEP_FULL` and any log-shipper
retention **must be set to the legally required period for the audit and call
documentation** before go-live. The platform does not impose a default.

## Not covered here

- The BKU-session and remote-control flows (#11–12) — completed with Epic 10 and
  its co-determination process.
- Cross-border transfer, sub-processor lists — deployment-specific.
