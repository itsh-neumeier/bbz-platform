"""client_popup_events schema (E15-03)."""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.client_popup_events import ClientPopupEvent


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


def _in(minutes: int) -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC) + _dt.timedelta(minutes=minutes)


async def test_defaults(s: AsyncSession) -> None:
    p = ClientPopupEvent(workplace_id=uuid.uuid4(), kind="incoming_call", expires_at=_in(2))
    s.add(p)
    await s.commit()
    await s.refresh(p)
    assert p.payload == {}
    assert p.delivered_at is None and p.dismissed_at is None
    assert p.created_at is not None


async def test_workplace_binding_is_mandatory(s: AsyncSession) -> None:
    s.add(ClientPopupEvent(kind="technical_alarm", expires_at=_in(1)))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_expiry_is_mandatory(s: AsyncSession) -> None:
    s.add(ClientPopupEvent(workplace_id=uuid.uuid4(), kind="door"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_payload_round_trips_and_lifecycle_timestamps_can_be_set(s: AsyncSession) -> None:
    wp = uuid.uuid4()
    p = ClientPopupEvent(
        workplace_id=wp,
        kind="technical_alarm",
        payload={"endpoint": "BMA Halle 3", "priority": "critical"},
        expires_at=_in(5),
    )
    s.add(p)
    await s.commit()

    p.delivered_at = _dt.datetime.now(_dt.UTC)
    p.dismissed_at = _dt.datetime.now(_dt.UTC)
    await s.commit()
    await s.refresh(p)
    assert p.payload["priority"] == "critical"
    assert p.delivered_at is not None and p.dismissed_at is not None
