# ADR-0025: Door-open DTMF flow — BBZ owns the secret, the sequence crosses the provider boundary

## Status
Accepted (2026-08-31, review E17-05 / #369)

## Context
MASTER_PROMPT §30 and `.ai/INTEGRATIONS_SIEDLE.md` require Siedle door opening to
run over the existing telephony integration: answer the doorbell call if needed,
wait for media, send a **configured DTMF sequence**, wait a short delay, hang up,
audit the result — transactional and idempotent, and **never** with the raw code
in an audit/event/log payload.

Two earlier decisions now collide:

- The foundation-phase `TelephonyProvider.send_dtmf(*, call_id, dtmf_profile_id,
  command_id)` protocol (E11-02) carries the note *"the raw code is a secret held
  by the integration/config store"* — read at the time as an **integration-side**
  store keyed by a profile reference. `telephony_sip/config_schema.json` still
  says "the raw code stays in the secret store".
- E17-01 / E17-02 (Phase 5, merged) instead built the store **inside BBZ**:
  `door_action_profiles.dtmf_ciphertext` (Fernet, `BBZ_DOOR_DTMF_ENCRYPTION_KEY`),
  managed through `/api/v1/door-action-profiles` (`door.configure`), with
  `DoorActionProfileService.resolve_dtmf()` written explicitly "for the door-open
  flow (E17-05)". A `technical_endpoint` references a profile by
  `dtmf_profile_id`.

The import-linter contract "core never imports concrete integrations" (and its
converse — `integrations/*` must not import `bbz_core`) means a telephony
provider **cannot** resolve a BBZ `door_action_profiles` id to digits. So once
BBZ holds the encrypted code, either the profile abstraction is duplicated into
every provider's own config, or the resolved sequence has to cross the boundary.

The real DTMF transports — Cisco JTAPI `MediaTerminalConnection` (E12-05) and SIP
INFO / RFC 2833 (E13-06) — are both in **blocked** epics. `telephony_mock`
(E11-05) has a synchronous, `command_id`-idempotent `send_dtmf`.

ADR-0024 already flagged this: *"automatic door opening (Epic 17) will need its
own latency review and may add a synchronous fast-path then."*

## Decision

1. **BBZ's `door_action_profiles` is the authoritative DTMF secret/config store**
   for telephony door opening. The code is Fernet-encrypted at rest, decrypted
   only transiently on the open path, and never persisted elsewhere, logged, or
   placed in an outbox/domain-event/audit payload. This satisfies §30 ("der
   konkrete Code ist Konfiguration/Secret und wird NICHT im Core hardcodiert") —
   an encrypted, admin-managed row is configuration, not hardcoding. The
   production KMS/secret-store backing is ADR-0015 / ADR-0019 / Epic 23;
   `bbz_core.infra.door_secrets` is the seam.

2. **The DTMF sequence — not a profile reference — crosses the `TelephonyProvider`
   boundary.** `DoorOpenService` resolves the profile via `resolve_dtmf()` and
   passes the digit string to the provider. Rationale: the provider is the
   component that physically emits DTMF and, per the architecture boundary,
   cannot resolve a BBZ reference. Providers are already bound by ADR-0004 /
   SECURITY.md to never log or echo the sequence.

3. **SDK change:** `TelephonyProvider.send_dtmf(*, call_id, dtmf, command_id)` —
   `dtmf` is the sequence to emit (renamed from `dtmf_profile_id`). `telephony_mock`
   stops echoing the argument in its `CommandAccepted.detail`. `telephony_sip`
   scaffold + `config_schema.json` wording updated. E15-08's `send_dtmf_profile`
   **trigger action** keeps carrying `dtmf_profile_id` (a bare id, not a secret)
   in its outbox row; its dispatcher — deferred until a real transport exists —
   will resolve profile → sequence at dispatch, exactly as E17-05 does.

4. **The open flow is synchronous** (the operator needs a "did it open?" answer),
   guarded by the durable idempotency-command (`X-Command-Id`, ADR-0012) **and** a
   persisted `door_open_commands` state machine (`requested → answering →
   connecting → dtmf_sent → completing → done | failed | timed_out`). Each
   provider step uses a **derived deterministic `command_id`**
   (`door:<command_id>:answer|dtmf|hangup`) — the "Ausführungsschlüssel" — so a
   retry is exactly-once at the provider too. `send_dtmf` fires **once**: guarded
   by the state row (`dtmf_sent_at is not None`) and the provider's own
   `command_id` dedupe. Steps: authorize `door.open` → (answer if ringing) →
   await CONNECTED up to `door_open_timeout_seconds` → `send_dtmf` once →
   `post_dtmf_delay_ms` → (auto-hangup) → audited result. `door.open` is the sole
   gate for E17-05 — the auto-answer is a mechanical step of opening, not the
   discretionary "Sprechen" action; finer `door.answer` enforcement and the rest
   of the failure matrix (auth-denied, no-media, failover, …) are E17-07's scope.

5. **Audit:** `DOOR_OPEN_REQUESTED` and `DOOR_OPEN_RESULT` (both critical) carry
   `technical_endpoint_id`, `door_action_profile_id`, `call_id`, `outcome`,
   `command_id` — **never** the sequence. E17-06 adds the cross-sink redaction
   contract test.

6. **Validated against `telephony_mock`.** The real JTAPI/SIP `send_dtmf`
   transport is E12-05 / E13-06 (blocked); the orchestration, idempotency, state
   machine, timeout handling and audit are transport-independent and testable now.

## Consequences
- `resolve_dtmf()` is now on the hot path; every caller must treat its result as
  a secret (no logging, no exception messages containing it).
- One new table (`door_open_commands`) and one synchronous endpoint
  (`POST /api/v1/doors/{endpoint_id}/open`) to run and monitor.
- The SDK `send_dtmf` rename touches the protocol, the mock, the SIP scaffold and
  their tests — a one-time mechanical change; CI's protocol conformance test
  covers it.
- `telephony_sip/config_schema.json` no longer implies an integration-side secret
  store; a real SIP adapter receives the sequence like any other provider.
- A future dedicated `door.*` transport capability could replace the raw-sequence
  hand-off with something narrower; out of scope here.
- Latency: the open path does real provider round-trips + `post_dtmf_delay_ms`
  inside the request. Acceptable for an operator-initiated action; a trigger-rule
  auto-open (E15-08 dispatcher) will reuse `DoorOpenService` from a worker.

## Alternatives considered
**Integration-side profile store** (the original protocol reading) — rejected: it
contradicts the merged E17-01/E17-02 admin UX, and would copy the secret into
every provider instance's config, losing the single encrypted-at-rest row and its
audit trail.

**Pass the BBZ profile id to the provider** — rejected: the provider cannot
resolve it (import boundary), and it is pointless once BBZ has already decrypted.

**Pure outbox orchestration with a door-open worker** — deferred: the flow needs
a synchronous operator result; the mock is synchronous; a worker adds no
exactly-once guarantee beyond the idempotency-command + state machine + derived
provider `command_id`s, and would block any real test on the (blocked) real
transport. The state machine row is kept so a worker-driven auto-open (E15-08)
can share it later.

**Keep the `dtmf_profile_id` parameter name, pass digits through it** — rejected:
a parameter named `…_profile_id` receiving a raw secret is a footgun; the mock
would echo it into `CommandAccepted.detail`, exactly the leak SECURITY.md forbids.
