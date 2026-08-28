# ADR-0009: Implementation Language for the Local Agents

## Status
Proposed — decision pending (see `.ai/CURRENT_STATE.md` open questions)

## Context
Two native local services are needed (MASTER_PROMPT §6, §28, ADR-0003):
`bbz-client-agent` (BBZ workplace PC) and `bku-agent` (BKU workstation). Both run
as a Windows service, do server discovery/health/failover, hold an encrypted
local cache and offline outbox, use a client certificate, and expose a strict
typed command surface — no arbitrary execution.

## Decision (proposed)
Use **Go** for both agents:
- first-class Windows service support and cross-compilation,
- small static binaries, straightforward signed-update story,
- simpler contributor onboarding than Rust for this team.
Reconsider Rust for a component only if a hard requirement (e.g. memory-safety
critical parsing of untrusted external protocol data) emerges.

## Consequences
- One language for both agents; shared internal libraries (discovery, outbox,
  command envelope).
- GC pauses are irrelevant at this workload; acceptable.

## Alternatives considered
Rust (stronger guarantees, steeper curve, slower iteration here); .NET (good
Windows integration but heavier runtime footprint on the endpoint).
