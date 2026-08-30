"""contacts / contact_numbers / contact_priorities schema (E14-01)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.contacts import Contact, ContactNumber, ContactPriority


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _contact(s: AsyncSession, name: str = "EVU Leitstelle") -> uuid.UUID:
    c = Contact(name=name)
    s.add(c)
    await s.flush()
    cid = c.id
    await s.commit()
    return cid


async def test_contact_defaults(s: AsyncSession) -> None:
    c = Contact(name="Siedle Service")
    s.add(c)
    await s.commit()
    await s.refresh(c)
    assert c.quick_dial is False
    assert c.org is None and c.notes is None and c.bbz_id is None
    assert c.created_at is not None


@pytest.mark.parametrize("bad", ["0911500", "+49 911 500", "tel:+49911", "+0911500", "+4", ""])
async def test_contact_number_must_be_stored_as_e164(s: AsyncSession, bad: str) -> None:
    cid = await _contact(s)
    s.add(ContactNumber(contact_id=cid, e164=bad))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


@pytest.mark.parametrize("ok", ["+49911500", "+4930123456789", "+41443334455"])
async def test_valid_e164_numbers_are_accepted(s: AsyncSession, ok: str) -> None:
    cid = await _contact(s)
    s.add(ContactNumber(contact_id=cid, e164=ok, label="Zentrale"))
    await s.commit()


async def test_a_number_is_unique_per_contact_but_may_repeat_across_contacts(
    s: AsyncSession,
) -> None:
    a = await _contact(s, "Kontakt A")
    b = await _contact(s, "Kontakt B")
    s.add(ContactNumber(contact_id=a, e164="+49911500"))
    await s.commit()

    s.add(ContactNumber(contact_id=a, e164="+49911500"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    # a shared switchboard number may legitimately belong to two contacts
    s.add(ContactNumber(contact_id=b, e164="+49911500"))
    await s.commit()


async def test_numbers_cascade_when_the_contact_is_deleted(s: AsyncSession) -> None:
    cid = await _contact(s)
    s.add(ContactNumber(contact_id=cid, e164="+49911500"))
    await s.commit()

    await s.delete(await s.get(Contact, cid))
    await s.commit()
    left = (
        (await s.execute(select(ContactNumber).where(ContactNumber.contact_id == cid)))
        .scalars()
        .all()
    )
    assert left == []


async def test_priority_level_is_constrained(s: AsyncSession) -> None:
    cid = await _contact(s)
    s.add(ContactPriority(contact_id=cid, priority="urgent"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    s.add(ContactPriority(contact_id=cid, priority="high"))
    await s.commit()


async def test_only_one_priority_row_per_contact(s: AsyncSession) -> None:
    cid = await _contact(s)
    s.add(ContactPriority(contact_id=cid, priority="low"))
    await s.commit()
    s.expunge_all()

    s.add(ContactPriority(contact_id=cid, priority="high"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_priority_cascades_when_the_contact_is_deleted(s: AsyncSession) -> None:
    cid = await _contact(s)
    s.add(ContactPriority(contact_id=cid, priority="medium"))
    await s.commit()

    await s.delete(await s.get(Contact, cid))
    await s.commit()
    assert await s.get(ContactPriority, cid) is None
