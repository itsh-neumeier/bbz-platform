# ADR process

Architecture Decision Records live in `.ai/DECISIONS/` (they are part of the
vendor-neutral source of truth). This file is just the process.

## When you need an ADR

Any change that alters an architecture decision — data model shape, HA behavior,
a provider contract, a security boundary, a technology choice. `.ai/RULES.md`:
**no silent architecture changes**.

## How

1. Copy `.ai/DECISIONS/ADR-0000-TEMPLATE.md` to the next number.
2. Status starts `Proposed`. Open a PR (label `adr`).
3. On merge, set `Accepted` (or `Superseded by ADR-XXXX`).
4. Never edit an accepted ADR's decision — supersede it with a new one.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | Two active app nodes + quorum-governed DB failover | Accepted |
| 0002 | Cisco CUCM telephony via JTAPI gateway | Accepted (baseline) |
| 0003 | Dedicated BKU agent bound to workplace | Accepted |
| 0004 | Technical endpoints + typed trigger rules | Accepted |
| 0005 | Versioned EPK-style workflow engine | Accepted |
| 0006 | Coda Video as video + alarm source | Accepted |
| 0007 | Monorepo layout and tooling | Proposed |
| 0008 | Backend stack and module boundaries | Proposed |
| 0009 | Agent implementation language (Go) | Proposed |
| 0010 | Safe restricted rule DSL | Proposed |
| 0011 | Event log + state tables, outbox/inbox | Proposed |
| 0012 | API and idempotency conventions | Proposed |
| 0013 | Frontend stack and a11y baseline | Proposed |
| 0014 | CI/CD and supply chain | Proposed |
| 0015 | Configuration and secrets management | Proposed |
| 0016 | Canonical naming: Coda Video not "Cayuga" | Accepted |
| 0017 | Time handling (UTC everywhere) | Proposed |
| 0018 | Distributed config store (etcd) | Proposed |
| 0020 | Audit / event-log immutability (append-only trigger) | Proposed |
| 0021 | PostgreSQL replication mode (synchronous + auto fallback) | Accepted |
