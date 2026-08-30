# ADR-0009: Implementation Language for the Local Agents

## Status
Accepted (2026-08-30, E09-01). Supersedes the earlier "Proposed — decision
pending".

## Context
Two native local services are needed (MASTER_PROMPT §6, §28, ADR-0003):
`bbz-client-agent` (BBZ workplace PC) and `bku-agent` (BKU workstation). Both run
as a Windows service, do server discovery/health/failover, hold an encrypted
local cache and offline outbox, use a client certificate, and expose a strict
typed command surface — no arbitrary execution.

The open question in `.ai/CURRENT_STATE.md` was **Go vs. Rust** for these agents.

## Decision
Use **Go** for both agents.

- First-class Windows service support (`golang.org/x/sys/windows/svc`) and
  trivial cross-compilation from the CI Linux runners to `windows/amd64`.
- Small static binaries, no runtime to deploy on the endpoint; a straightforward
  signed-update story (detached signature over the binary, verified before
  swap).
- Simpler contributor onboarding than Rust for this team; faster iteration on
  the discovery/outbox/command loop, which is I/O-bound plumbing, not
  CPU-critical or memory-unsafe parsing.

Rust is reconsidered **per component** only if a hard requirement emerges — for
example memory-safety-critical parsing of untrusted external protocol data on
the endpoint. None of the planned agent work meets that bar: the agents speak
only to the BBZ server over mTLS with a typed, server-defined command envelope.

.NET was rejected: good Windows integration but a heavier runtime footprint on
the endpoint and a larger attack surface than a single static binary.

## Consequences

### One language, shared internal libraries
Both agents are built from the same Go module workspace with shared internal
packages. The three that matter for the roadmap:

| Shared lib | Responsibility | First consumed by |
|---|---|---|
| `discovery` | SRV01/SRV02 endpoint discovery, health probing, active-node selection, reconnect/backoff | E09-04, E10-05 |
| `outbox` | encrypted local cache + append-only offline outbox, at-least-once flush with idempotency keys, replay-safe against a server failover | E09-06, E10-05 |
| `commandenvelope` | the typed command envelope (`command_id`, `expires_at`, `generation`, correlation id), signature/replay checks, the closed command-type registry — **no** arbitrary shell/URL/exec path | E09-08, E10-04, E10-13 |

These live in `services/bbz-agents/` (Go workspace) with `bbz-client-agent/` and
`bku-agent/` as the two `main` packages. The command-envelope wire format is
kept in lockstep with the server side (`bbz_core` idempotency / ADR-0012) and
with `packages/event-schemas` where payloads overlap — the Go types are
generated from / checked against the same JSON Schemas in CI, so the contract
has one source of truth.

### Build & supply chain
- Go toolchain pinned in CI; `govulncheck` in the security job (parallel to
  `pip-audit` / `trivy`); `CGO_ENABLED=0` static builds.
- Agent releases are versioned independently of the server but declare a
  minimum server API version.

### Not in scope here
Agent implementation (E09-02 ff., E10-05 ff.), the enrollment/identity design
(E10-03, E09-08), and the signed-update mechanism details (E09-10).

## Alternatives considered
Rust (stronger compile-time guarantees, steeper curve, slower iteration for this
plumbing-heavy workload); .NET (good Windows integration, heavier endpoint
runtime and attack surface).
