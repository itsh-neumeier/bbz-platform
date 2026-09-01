"""monitor_inputs / monitor_outputs / monitor_routes / monitor_profiles schema
(roadmap E19-01, MASTER_PROMPT §9). Schema shape + constraints only — the fixed
catalog and standard layout are E19-02."""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import Base
from bbz_core.infra.models.identity import User
from bbz_core.infra.models.monitor import (
    MonitorInput,
    MonitorOutput,
    MonitorProfile,
    MonitorRoute,
)

_NOW = _dt.datetime(2026, 9, 1, 12, 0, tzinfo=_dt.UTC)


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _user(s: AsyncSession, name: str = "op") -> uuid.UUID:
    u = User(display_name=name)
    s.add(u)
    await s.flush()
    return u.id


async def _input(s: AsyncSession, key: str = "bbz-os") -> MonitorInput:
    i = MonitorInput(key=key, label=key.upper())
    s.add(i)
    await s.flush()
    return i


async def _output(s: AsyncSession, key: str, *, row: int | None, col: int | None) -> MonitorOutput:
    o = MonitorOutput(key=key, label=key, grid_row=row, grid_col=col, is_large_display=row is None)
    s.add(o)
    await s.flush()
    return o


def test_all_four_tables_are_registered() -> None:
    assert {
        "monitor_inputs",
        "monitor_outputs",
        "monitor_routes",
        "monitor_profiles",
    } <= set(Base.metadata.tables)


async def test_the_3x2_grid_plus_a_large_display_is_representable(s: AsyncSession) -> None:
    for n, (r, c) in enumerate([(row, col) for row in (0, 1) for col in (0, 1, 2)], start=1):
        await _output(s, f"workplace{n}", row=r, col=c)
    await _output(s, "large-display", row=None, col=None)
    await s.commit()

    outs = {o.key: o for o in (await s.execute(select(MonitorOutput))).scalars()}
    grid = {(o.grid_row, o.grid_col) for o in outs.values() if not o.is_large_display}
    assert grid == {(r, c) for r in (0, 1) for c in (0, 1, 2)}
    assert outs["large-display"].grid_row is None and outs["large-display"].is_large_display


async def test_a_grid_slot_is_unique(s: AsyncSession) -> None:
    await _output(s, "a", row=1, col=0)
    with pytest.raises(IntegrityError):
        await _output(s, "b", row=1, col=0)  # same slot
    await s.rollback()


async def test_the_grid_check_rejects_a_bad_position(s: AsyncSession) -> None:
    s.add(MonitorOutput(key="x", label="X", grid_row=0, grid_col=3, is_large_display=False))
    with pytest.raises(IntegrityError):  # col out of 0..2
        await s.commit()
    await s.rollback()

    s.add(MonitorOutput(key="y", label="Y", grid_row=0, grid_col=0, is_large_display=True))
    with pytest.raises(IntegrityError):  # a large display has no grid slot
        await s.commit()
    await s.rollback()


async def test_exactly_one_route_per_output(s: AsyncSession) -> None:
    out = await _output(s, "workplace1", row=0, col=0)
    a, b = await _input(s, "bku1"), await _input(s, "bku2")
    s.add(MonitorRoute(output_id=out.id, input_id=a.id, set_at=_NOW))
    await s.commit()

    s.add(MonitorRoute(output_id=out.id, input_id=b.id, set_at=_NOW))
    with pytest.raises(IntegrityError):  # output_id is the PK
        await s.commit()
    await s.rollback()


async def test_a_route_survives_its_setter_being_deleted(s: AsyncSession) -> None:
    uid = await _user(s)
    out = await _output(s, "workplace1", row=0, col=0)
    inp = await _input(s)
    s.add(MonitorRoute(output_id=out.id, input_id=inp.id, set_by=uid, set_at=_NOW))
    await s.commit()

    await s.execute(User.__table__.delete().where(User.id == uid))
    await s.commit()
    r = (await s.execute(select(MonitorRoute).where(MonitorRoute.output_id == out.id))).scalar_one()
    assert r.set_by is None and r.input_id == inp.id


async def test_an_input_still_routed_cannot_be_deleted(s: AsyncSession) -> None:
    out = await _output(s, "workplace1", row=0, col=0)
    inp = await _input(s, "bku1")
    s.add(MonitorRoute(output_id=out.id, input_id=inp.id, set_at=_NOW))
    await s.commit()

    with pytest.raises(IntegrityError):  # ondelete=RESTRICT
        await s.execute(MonitorInput.__table__.delete().where(MonitorInput.id == inp.id))
    await s.rollback()


async def test_deleting_an_output_takes_its_route_with_it(s: AsyncSession) -> None:
    out = await _output(s, "workplace1", row=0, col=0)
    inp = await _input(s)
    s.add(MonitorRoute(output_id=out.id, input_id=inp.id, set_at=_NOW))
    await s.commit()

    await s.execute(MonitorOutput.__table__.delete().where(MonitorOutput.id == out.id))
    await s.commit()
    assert (await s.execute(select(MonitorRoute))).first() is None  # CASCADE


async def test_a_user_profile_needs_an_owner_and_no_workplace(s: AsyncSession) -> None:
    uid = await _user(s)
    s.add(
        MonitorProfile(
            name="Frühdienst", scope="user", owner_user_id=uid, layout={"workplace1": "bku1"}
        )
    )
    await s.commit()

    s.add(MonitorProfile(name="bad", scope="user", layout={}))  # no owner
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    s.add(
        MonitorProfile(
            name="bad2",
            scope="workplace",
            owner_user_id=uid,  # workplace scope must not carry an owner
            workplace_id=uuid.uuid4(),
            layout={},
        )
    )
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_an_unknown_profile_scope_is_rejected(s: AsyncSession) -> None:
    s.add(MonitorProfile(name="p", scope="global", workplace_id=uuid.uuid4(), layout={}))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_a_route_can_reference_the_profile_it_came_from(s: AsyncSession) -> None:
    uid = await _user(s)
    out = await _output(s, "workplace1", row=0, col=0)
    inp = await _input(s)
    prof = MonitorProfile(name="p", scope="user", owner_user_id=uid, layout={})
    s.add(prof)
    await s.flush()
    s.add(
        MonitorRoute(output_id=out.id, input_id=inp.id, set_by=uid, set_at=_NOW, profile_id=prof.id)
    )
    await s.commit()

    await s.execute(MonitorProfile.__table__.delete().where(MonitorProfile.id == prof.id))
    await s.commit()
    r = (await s.execute(select(MonitorRoute))).scalar_one()
    assert r.profile_id is None  # SET NULL — the route stays
