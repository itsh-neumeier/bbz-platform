# ADR-0004: Technical Telephony Endpoints and Typed Trigger Rules

## Status
Accepted

## Context
Some inbound telephone numbers represent machines rather than human contacts. Examples are Siedle door stations and BMA dialers. Their calls must trigger deterministic technical workflows.

## Decision
Model technical endpoints separately from the telephone book and evaluate versioned typed trigger rules on normalized telephony events. External actions use durable idempotent outbox execution.

## Consequences
- human contacts remain clean
- technical number -> process mapping is administrable
- active/active duplicate handling can be made exactly-once at side-effect level
- Siedle and BMA use the same generic mechanism without hardcoding each process into the telephony UI
