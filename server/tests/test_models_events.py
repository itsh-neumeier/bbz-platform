"""Event-core schema shape + a DB roundtrip."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import (
    Base,
    Event,
    EventAssignment,
    EventNote,
    EventStatus,
    EventStatusHistory,
)


def test_tables_and_checks_registered() -> None:
    assert {
        "events",
        "event_status_history",
        "event_assignments",
        "event_notes",
    } <= set(Base.metadata.tables)
    checks = {
        c.name for c in Event.__table__.constraints if c.__class__.__name__ == "CheckConstraint"
    }
    assert {"ck_events_event_priority", "ck_events_event_status"} <= checks


def test_cascades() -> None:
    for model, col in (
        (EventStatusHistory, "event_id"),
        (EventAssignment, "event_id"),
        (EventNote, "event_id"),
    ):
        fk = next(f for f in model.__table__.foreign_keys if f.parent.name == col)
        assert fk.ondelete == "CASCADE"


async def test_event_roundtrip_and_one_active_assignment(db: object) -> None:
    from bbz_core.infra.models.identity import User

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)

    u1, u2 = User(display_name="A"), User(display_name="B")
    s.add_all([u1, u2])
    await s.flush()
    u1_id, u2_id = u1.id, u2.id

    ev = Event(title="Rauchentwicklung Bahnsteig 4", priority="high")
    s.add(ev)
    await s.flush()
    ev_id = ev.id
    assert ev.version == 1
    assert ev.status == EventStatus.NEW.value

    s.add(EventStatusHistory(event_id=ev_id, from_status=None, to_status="new"))
    s.add(EventAssignment(event_id=ev_id, user_id=u1_id, active=True))
    await s.commit()

    # a second *active* assignment for the same event is rejected
    s.add(EventAssignment(event_id=ev_id, user_id=u2_id, active=True))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    # an inactive one is fine
    s.add(EventAssignment(event_id=ev_id, user_id=u2_id, active=False))
    await s.commit()
    rows = (
        (await s.execute(select(EventAssignment).where(EventAssignment.event_id == ev_id)))
        .scalars()
        .all()
    )
    assert sum(r.active for r in rows) == 1


async def test_deleting_event_cascades(db: object) -> None:
    from bbz_core.infra.models.identity import User

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    u = User(display_name="C")
    s.add(u)
    await s.flush()
    ev = Event(title="x", priority="low")
    s.add(ev)
    await s.flush()
    s.add(EventNote(event_id=ev.id, kind="work", body="note", created_by=u.id))
    await s.commit()

    await s.delete(ev)
    await s.commit()
    left = (await s.execute(select(EventNote).where(EventNote.event_id == ev.id))).all()
    assert left == []
