"""ADR-0020: audit_events / domain_events are append-only at the DB level (E04-10).

Uses raw SQL to bypass the ORM guard (E04-01) and hit the trigger directly.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.event_log import append_event


async def _one_audit_row(s: AsyncSession) -> uuid.UUID:
    async with s.begin():
        rid = (
            await s.execute(
                text(
                    "INSERT INTO audit_events (node_id, action) "
                    "VALUES ('BBZ-TEST', 'LOGIN_SUCCEEDED') RETURNING id"
                )
            )
        ).scalar_one()
    return uuid.UUID(str(rid))


async def test_raw_update_on_audit_events_is_blocked(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    rid = await _one_audit_row(s)
    with pytest.raises(DBAPIError, match="append-only table"):
        async with s.begin():
            await s.execute(
                text("UPDATE audit_events SET reason = 'tamper' WHERE id = :i"), {"i": rid}
            )
    await s.rollback()


async def test_raw_delete_on_audit_events_is_blocked(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    rid = await _one_audit_row(s)
    with pytest.raises(DBAPIError, match="append-only table"):
        async with s.begin():
            await s.execute(text("DELETE FROM audit_events WHERE id = :i"), {"i": rid})
    await s.rollback()


async def test_raw_update_and_delete_on_domain_events_are_blocked(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        seq = await append_event(
            s,
            aggregate_type="event",
            aggregate_id=uuid.uuid4(),
            event_type="EVENT_CREATED",
            payload={"title": "x", "priority": "high", "actor_id": "u1"},
        )

    with pytest.raises(DBAPIError, match="append-only table"):
        async with s.begin():
            await s.execute(
                text("UPDATE domain_events SET payload = '{}'::jsonb WHERE event_seq = :s"),
                {"s": seq},
            )
    await s.rollback()

    with pytest.raises(DBAPIError, match="append-only table"):
        async with s.begin():
            await s.execute(text("DELETE FROM domain_events WHERE event_seq = :s"), {"s": seq})
    await s.rollback()


async def test_insert_still_works(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    rid = await _one_audit_row(s)
    got = (
        await s.execute(text("SELECT action FROM audit_events WHERE id = :i"), {"i": rid})
    ).scalar_one()
    assert got == "LOGIN_SUCCEEDED"
