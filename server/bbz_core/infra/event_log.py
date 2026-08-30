"""Append to the domain-event log — only inside a running transaction.

``append_event`` writes one row in the caller's transaction (so it commits or
rolls back together with the state change — ADR-0011), assigns ``event_seq``
via the DB identity, and validates the resulting envelope against
``domain_event.envelope.v1`` before returning.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from functools import lru_cache
from typing import Any

import jsonschema
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.logging import correlation_id
from bbz_core.settings import get_settings
from bbz_event_schemas import UnknownEventTypeError as _SchemaUnknownEventType
from bbz_event_schemas import event_payload_schema, load_schema

_ENVELOPE = "domain_event.envelope.v1"


class NotInTransactionError(RuntimeError):
    """append_event was called outside a DB transaction (ADR-0011 invariant)."""


class EnvelopeInvalidError(ValueError):
    pass


class UnknownEventTypeError(EnvelopeInvalidError):
    """The event_type has no registered payload schema (ADR-0011) — rejected."""


@lru_cache
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        load_schema(_ENVELOPE), format_checker=jsonschema.FormatChecker()
    )


@lru_cache
def _payload_validator(event_type: str, schema_version: int) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        event_payload_schema(event_type, schema_version),
        format_checker=jsonschema.FormatChecker(),
    )


def envelope(row: DomainEvent) -> dict[str, Any]:
    """The row rendered as a ``domain_event.envelope.v1`` dict (streams reuse this)."""
    return {
        "event_seq": row.event_seq,
        "event_uuid": str(row.event_uuid),
        "aggregate_type": row.aggregate_type,
        "aggregate_id": row.aggregate_id,
        "event_type": row.event_type,
        "occurred_at_utc": row.occurred_at_utc.astimezone(_dt.UTC).isoformat(),
        "occurred_at_local": row.occurred_at_local,
        "node_id": row.node_id,
        "user_id": str(row.user_id) if row.user_id else None,
        "client_id": row.client_id,
        "command_id": str(row.command_id) if row.command_id else None,
        "correlation_id": row.correlation_id,
        "schema_version": row.schema_version,
        "payload": row.payload,
    }


async def append_event(
    session: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: str | uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    schema_version: int = 1,
    user_id: uuid.UUID | None = None,
    client_id: str | None = None,
    command_id: uuid.UUID | None = None,
    occurred_at_local: str | None = None,
) -> int:
    if not session.in_transaction():
        raise NotInTransactionError(
            "append_event must run inside the same transaction as the state change"
        )
    row = DomainEvent(
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        event_type=event_type,
        occurred_at_utc=_dt.datetime.now(_dt.UTC),
        occurred_at_local=occurred_at_local,
        node_id=get_settings().node_id,
        user_id=user_id,
        client_id=client_id,
        command_id=command_id,
        correlation_id=correlation_id.get(),
        schema_version=schema_version,
        payload=payload,
    )
    session.add(row)
    await session.flush()  # assigns event_seq
    errors = sorted(_validator().iter_errors(envelope(row)), key=str)
    if errors:
        raise EnvelopeInvalidError("; ".join(e.message for e in errors))
    try:
        payload_validator = _payload_validator(row.event_type, row.schema_version)
    except _SchemaUnknownEventType as exc:
        raise UnknownEventTypeError(str(exc)) from exc
    payload_errors = sorted(payload_validator.iter_errors(row.payload), key=str)
    if payload_errors:
        raise EnvelopeInvalidError(
            f"{row.event_type} payload: " + "; ".join(e.message for e in payload_errors)
        )
    return row.event_seq


async def head_seq(session: AsyncSession) -> int:
    """Highest assigned ``event_seq`` (0 on an empty log). ``event_seq`` is
    monotonic but **not gapless** — a Patroni failover can skip a range of
    identity values without losing any committed row (see docs/client-catchup)."""
    value: int = (
        await session.execute(select(func.coalesce(func.max(DomainEvent.event_seq), 0)))
    ).scalar_one()
    return value


async def read_since(
    session: AsyncSession, after_seq: int, *, limit: int = 500
) -> list[DomainEvent]:
    return list(
        (
            await session.execute(
                select(DomainEvent)
                .where(DomainEvent.event_seq > after_seq)
                .order_by(DomainEvent.event_seq)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
