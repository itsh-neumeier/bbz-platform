"""Infrastructure adapters: database, repositories, event store, outbox/inbox.

Phase 0 wires only the async SQLAlchemy engine and a readiness probe. The event
store, durable outbox and provider-event inbox (required for active/active
exactly-once, ADR-0004/0006/0011) are implemented in Phase 1.
"""
