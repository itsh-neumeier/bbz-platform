# Audit-log integrity — the hash chain

Roadmap **E23-09**, MASTER_PROMPT §17, extends **E04-10**.
`bbz_core.infra.repositories.audit_chain`.

`audit_events` is already **append-only** — an `ORM` guard (E04-01) and a
`BEFORE UPDATE OR DELETE` trigger (0016 / ADR-0020) block any row mutation from
any client. That stops the ordinary paths. The hash chain adds **detection** for
the rest: a DBA with `session_replication_role = replica`, a restore from a
doctored dump, storage-level corruption.

## How it works

`audit_events` has a monotonic `seq` (a BIGINT identity — insertion order). A
leader-elected worker (`audit-chain`, every `BBZ_AUDIT_CHAIN_INTERVAL_SECONDS`,
default 300 s) **seals** each new row into `audit_chain_links`:

```
row_digest = sha256(canonical_json(seq, occurred_at, node_id, action, actor_*,
                                   target_*, before, after, reason,
                                   correlation_id, event_seq_ref))
row_hash   = sha256(prev_hash + row_digest)          # prev_hash of link 1 = 64×"0"
```

`audit_chain_links` is itself append-only. Sealing is **deferred** — it is not in
the audit-write transaction, so it adds **zero latency** to the action being
audited. A new row is unsealed for at most one interval.

The same worker then **verifies** the whole chain: re-read every link in `seq`
order, recompute `row_hash`, and check

- the recomputed hash still matches (row content unchanged),
- `prev_hash` equals the previous link's `row_hash` (no reordering / injection),
- `seq` has no gaps (no row removed after sealing),
- the linked `audit_events` row still exists.

Any failure logs `audit_integrity_alert` and writes an **`AUDIT_INTEGRITY_ALERT`**
audit row (a critical action) carrying the first bad `seq` and the reason.

## Reading / exporting the chain

`GET /api/v1/audit/chain` (`system.audit.view`) re-verifies and returns a page of
links (`after_seq` + `next_after_seq` for pagination). Archive the full export
alongside the audit rows for an independent, offline re-check — the chain only
needs the row content and the genesis constant to verify.

## Config

| env | default | meaning |
|---|---|---|
| `BBZ_AUDIT_HASH_CHAIN_ENABLED` | `true` | off ⇒ nothing is sealed or verified |
| `BBZ_AUDIT_CHAIN_INTERVAL_SECONDS` | `300` | seal + verify cadence |

## Overhead

Sealing is `O(new rows)` sha256 + one INSERT each, off the request path.
Verification is a full-table sha256 walk — on commodity hardware sha256 runs at
hundreds of MB/s, so a chain of millions of rows verifies in seconds; the worker
does it once per interval on the leader only. For a very large deployment,
`AuditChainService.verify(limit=…)` supports checking the tail more often and the
whole chain less often — not wired to config yet.

## HA

Both app nodes write `audit_events`; only the lease holder runs `audit-chain`, so
the chain is sealed exactly once. `audit_chain_links` replicates with the rest of
the database, so a promoted standby continues the same chain.

## WORM storage

Out of scope here (no WORM *hardware*). The export is the integration point: ship
it (append-only) to an object store with a retention lock / legal hold, or to a
write-once medium, for tamper-*evidence* that survives loss of the primary
database.
