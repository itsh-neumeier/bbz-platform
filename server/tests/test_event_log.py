"""domain-event log: in-tx invariant, monotonic seq, envelope validation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.event_log import (
    EnvelopeInvalidError,
    NotInTransactionError,
    UnknownEventTypeError,
    append_event,
    read_since,
)

_ACCEPTED = {"from": "new", "to": "accepted", "actor_id": str(uuid.uuid4())}


def _created(title: str = "Störung") -> dict[str, str]:
    return {"title": title, "priority": "high", "actor_id": str(uuid.uuid4())}


async def test_append_outside_transaction_raises(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    assert not s.in_transaction()
    with pytest.raises(NotInTransactionError):
        await append_event(
            s,
            aggregate_type="event",
            aggregate_id=uuid.uuid4(),
            event_type="EVENT_CREATED",
            payload=_created(),
        )


async def test_seq_is_monotonic_and_in_caller_tx(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    aid = uuid.uuid4()
    async with s.begin():
        seq1 = await append_event(
            s,
            aggregate_type="event",
            aggregate_id=aid,
            event_type="EVENT_CREATED",
            payload=_created(),
        )
        seq2 = await append_event(
            s,
            aggregate_type="event",
            aggregate_id=aid,
            event_type="EVENT_ACCEPTED",
            payload=_ACCEPTED,
            command_id=uuid.uuid4(),
        )
    assert seq2 > seq1

    rows = await read_since(s, seq1 - 1)
    assert [r.event_seq for r in rows] == [seq1, seq2]
    assert rows[0].node_id and rows[0].event_uuid


async def test_rollback_drops_the_event(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    try:
        async with s.begin():
            await append_event(
                s,
                aggregate_type="event",
                aggregate_id=uuid.uuid4(),
                event_type="EVENT_CREATED",
                payload=_created(),
            )
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert await read_since(s, 0) == []


async def test_bad_envelope_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(EnvelopeInvalidError):
        async with s.begin():
            await append_event(
                s,
                aggregate_type="event",
                aggregate_id=uuid.uuid4(),
                event_type="",  # violates minLength 1
                payload=_created(),
            )


async def test_unknown_event_type_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(UnknownEventTypeError):
        async with s.begin():
            await append_event(
                s,
                aggregate_type="event",
                aggregate_id=uuid.uuid4(),
                event_type="EVENT_TELEPORTED",
                payload={},
            )


async def test_payload_missing_required_field_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(EnvelopeInvalidError):
        async with s.begin():
            await append_event(
                s,
                aggregate_type="event",
                aggregate_id=uuid.uuid4(),
                event_type="EVENT_CREATED",
                payload={"title": "x"},  # no priority / actor_id
            )
