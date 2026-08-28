# ADR-0016: Canonical Naming — Coda Video (not "Cayuga")

## Status
Accepted

## Context
Early planning used "Cayuga" for the video platform. ADR-0006 and
`.ai/INTEGRATIONS_CODA_VIDEO.md` established `coda_video` (HxGN dC3 Video) as
canonical, but `.ai/INTEGRATIONS_CAYUGA.md` still existed as a byte-identical
duplicate and several documents (monitor inputs, feature notes) still said
"Cayuga".

## Decision
- `coda_video` is the only integration id. "Cayuga" is allowed solely as a
  migration/display alias where an existing environment requires it.
- `.ai/INTEGRATIONS_CAYUGA.md` becomes a short pointer to
  `.ai/INTEGRATIONS_CODA_VIDEO.md` (kept, not deleted, to preserve inbound links
  and history).
- New code/config/docs use `coda_video` / "Coda Video". Monitor input labels use
  `CODA1`/`CODA2`.
- No behavior change.

## Consequences
- One source of truth for the video/alarm integration; less drift.

## Alternatives considered
Delete the Cayuga file (rejected: breaks existing references and the paper trail).
