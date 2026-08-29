"""audit_events: append-only ORM mapping (E04-01)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent, AuditImmutableError


def test_all_master_prompt_17_columns_present() -> None:
    cols = set(AuditEvent.__table__.columns.keys())
    assert {
        "id",
        "occurred_at_utc",
        "actor_user_id",
        "actor_client_id",
        "workplace_id",
        "node_id",
        "action",
        "target_type",
        "target_id",
        "before",
        "after",
        "reason",
        "correlation_id",
        "event_seq_ref",
    } <= cols
    assert "updated_at" not in cols  # append-only: no mutation timestamp


async def _row(s: AsyncSession) -> AuditEvent:
    row = AuditEvent(node_id="BBZ-TEST", action="LOGIN_SUCCEEDED")
    s.add(row)
    await s.commit()
    return row


async def test_update_is_blocked(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    row = await _row(s)
    row.reason = "tampered"
    with pytest.raises(AuditImmutableError):
        await s.commit()
    await s.rollback()


async def test_delete_is_blocked(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    row = await _row(s)
    await s.delete(row)
    with pytest.raises(AuditImmutableError):
        await s.commit()
    await s.rollback()


async def test_insert_still_works(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    row = AuditEvent(
        node_id="BBZ-TEST",
        action="EVENT_TAKEN_OVER",
        target_type="event",
        target_id=str(uuid.uuid4()),
        before={"assignee_id": None},
        after={"assignee_id": str(uuid.uuid4())},
        event_seq_ref=42,
    )
    s.add(row)
    await s.commit()
    found = (await s.execute(select(AuditEvent).where(AuditEvent.id == row.id))).scalar_one()
    assert found.event_seq_ref == 42
