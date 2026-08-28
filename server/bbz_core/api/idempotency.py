"""Command / idempotency envelope.

MASTER_PROMPT §15 and RULES.md: *every* state-changing request carries a
``command_id`` (idempotency key), the acting user, client and workplace, and an
``expected_version`` for optimistic concurrency.

Phase 0 defines the envelope model and a FastAPI dependency that parses/validates
it from headers. The durable dedupe store (``commands`` table) and replay
protection land in Phase 1 (ADR-0011/0012) — this module raises ``NotImplemented``
paths nowhere; it simply does not yet persist.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import Header
from pydantic import BaseModel, Field


class CommandEnvelope(BaseModel):
    """Metadata that must accompany every write command."""

    command_id: UUID = Field(description="Client-generated idempotency key.")
    expected_version: int | None = Field(
        default=None, description="Optimistic concurrency guard; None only for creates."
    )
    client_id: str | None = None
    workplace_id: str | None = None
    correlation_id: str | None = None
    offline: bool = Field(
        default=False, description="True when the command was queued in the client outbox."
    )


async def command_envelope(
    x_command_id: UUID = Header(description="Idempotency key (UUID)."),
    x_expected_version: int | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
    x_workplace_id: str | None = Header(default=None),
    x_correlation_id: str | None = Header(default=None),
    x_offline: bool = Header(default=False),
) -> CommandEnvelope:
    return CommandEnvelope(
        command_id=x_command_id,
        expected_version=x_expected_version,
        client_id=x_client_id,
        workplace_id=x_workplace_id,
        correlation_id=x_correlation_id,
        offline=x_offline,
    )
