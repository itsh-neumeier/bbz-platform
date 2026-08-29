"""Event repository / unit-of-work: atomic state+event, optimistic concurrency."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.events import EventAggregate, EventPriority, EventStatus
from bbz_core.infra.event_log import read_since
from bbz_core.infra.models.events import EventAssignment, EventStatusHistory
from bbz_core.infra.repositories.events import (
    EventNotFoundError,
    EventRepository,
    EventRepositoryError,
    VersionConflictError,
)


async def _user(s: AsyncSession, name: str = "Operator") -> uuid.UUID:
    from bbz_core.infra.models.identity import User

    u = User(display_name=name)
    s.add(u)
    await s.flush()
    uid = u.id
    await s.commit()
    return uid


def _new(actor: uuid.UUID) -> EventAggregate:
    return EventAggregate.create(
        event_id=uuid.uuid4(),
        title="Signalstörung W12",
        priority=EventPriority.HIGH,
        actor_id=actor,
    )


async def _history(s: AsyncSession, event_id: uuid.UUID) -> list[tuple[str | None, str]]:
    rows = (
        (
            await s.execute(
                select(EventStatusHistory)
                .where(EventStatusHistory.event_id == event_id)
                .order_by(EventStatusHistory.changed_at)
            )
        )
        .scalars()
        .all()
    )
    return [(r.from_status, r.to_status) for r in rows]


async def test_add_writes_event_row_history_and_domain_event(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    uid = await _user(s)
    repo = EventRepository(s)
    agg = _new(uid)

    async with s.begin():
        version = await repo.add(agg, actor_id=uid)
    assert version == 1

    loaded = await repo.get(agg.id)
    assert loaded is not None
    assert loaded.status is EventStatus.NEW
    assert loaded.version == 1
    assert await _history(s, agg.id) == [(None, "new")]
    assert [r.event_type for r in await read_since(s, 0)] == ["EVENT_CREATED"]


async def test_save_bumps_version_and_appends_transition(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    uid = await _user(s)
    repo = EventRepository(s)
    agg = _new(uid)
    async with s.begin():
        await repo.add(agg, actor_id=uid)

    async with s.begin():
        reloaded = await repo.require(agg.id)
        reloaded.accept(uid)
        v2 = await repo.save(reloaded, actor_id=uid, expected_version=1)
    assert v2 == 2

    assert (await repo.require(agg.id)).status is EventStatus.ACCEPTED
    assert await _history(s, agg.id) == [(None, "new"), ("new", "accepted")]
    assert [r.event_type for r in await read_since(s, 0)] == [
        "EVENT_CREATED",
        "EVENT_ACCEPTED",
    ]


async def test_stale_expected_version_conflicts(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    uid = await _user(s)
    repo = EventRepository(s)
    agg = _new(uid)
    async with s.begin():
        await repo.add(agg, actor_id=uid)

    # two independent loads at version 1 (concurrent writers)
    first = await repo.require(agg.id)
    second = await repo.require(agg.id)
    await s.rollback()  # close the read transaction opened by the loads

    first.accept(uid)
    async with s.begin():
        await repo.save(first, actor_id=uid, expected_version=1)

    second.accept(uid)
    with pytest.raises(VersionConflictError):
        async with s.begin():
            await repo.save(second, actor_id=uid, expected_version=1)


async def test_rollback_leaves_neither_state_nor_event(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    uid = await _user(s)
    repo = EventRepository(s)
    agg = _new(uid)

    with pytest.raises(RuntimeError, match="boom"):
        async with s.begin():
            await repo.add(agg, actor_id=uid)
            raise RuntimeError("boom")

    assert await repo.get(agg.id) is None
    assert await read_since(s, 0) == []


async def test_require_missing_event_raises(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(EventNotFoundError):
        await EventRepository(s).require(uuid.uuid4())


async def test_writes_must_run_in_a_transaction(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    uid = await _user(s)
    with pytest.raises(EventRepositoryError):
        await EventRepository(s).add(_new(uid), actor_id=uid)


async def test_assignment_and_takeover_keep_one_active_row(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    owner = await _user(s, "Owner")
    u2 = await _user(s, "U2")
    u3 = await _user(s, "U3")
    repo = EventRepository(s)
    agg = _new(owner)
    async with s.begin():
        await repo.add(agg, actor_id=owner)

    async with s.begin():
        a = await repo.require(agg.id)
        a.assign(to_user_id=u2, actor_id=owner)
        await repo.save(a, actor_id=owner, expected_version=1)

    async with s.begin():
        a = await repo.require(agg.id)
        a.take_over(new_user_id=u3, actor_id=owner)
        await repo.save(a, actor_id=owner, expected_version=2)

    assert (await repo.require(agg.id)).assignee_id == u3
    active = (
        await s.execute(
            select(func.count())
            .select_from(EventAssignment)
            .where(EventAssignment.event_id == agg.id, EventAssignment.active.is_(True))
        )
    ).scalar_one()
    assert active == 1
    assert [r.event_type for r in await read_since(s, 0)] == [
        "EVENT_CREATED",
        "EVENT_ASSIGNED",
        "EVENT_TAKEN_OVER",
    ]
