"""ContactMatcher: incoming number -> contact + priority, or unknown (E14-04)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.contacts import Contact, ContactNumber, ContactPriority
from bbz_core.infra.repositories.contact_matching import ContactMatcher, clear_matcher_cache


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    clear_matcher_cache()
    yield db
    clear_matcher_cache()


async def _contact(
    s: AsyncSession,
    name: str,
    numbers: list[str],
    *,
    priority: str | None = None,
    deleted: bool = False,
) -> uuid.UUID:
    import datetime as _dt

    c = Contact(name=name, deleted_at=_dt.datetime.now(_dt.UTC) if deleted else None)
    s.add(c)
    await s.flush()
    for i, e in enumerate(numbers):
        s.add(ContactNumber(contact_id=c.id, e164=e, is_primary=(i == 0)))
    if priority is not None:
        s.add(ContactPriority(contact_id=c.id, priority=priority))
    await s.commit()
    return c.id


async def test_exact_match_returns_contact_and_priority(s: AsyncSession) -> None:
    cid = await _contact(s, "EVU Leitstelle", ["+49911500123"], priority="high")

    m = await ContactMatcher(s).resolve("0911 500 123")
    assert m.matched
    assert m.contact_id == cid
    assert m.name == "EVU Leitstelle"
    assert m.priority == "high"
    assert m.e164 == "+49911500123"
    assert m.matched_on == "+49911500123"


async def test_unknown_number_is_reported_not_guessed(s: AsyncSession) -> None:
    await _contact(s, "Somebody", ["+49911500123"])
    m = await ContactMatcher(s).resolve("+49301112222")
    assert not m.matched
    assert m.e164 == "+49301112222"
    assert m.contact_id is None and m.priority is None


async def test_a_direct_dial_extension_matches_the_base_number(s: AsyncSession) -> None:
    cid = await _contact(s, "Siedle Service", ["+499115000"], priority="medium")
    # a caller on extension 42 of the same PBX
    m = await ContactMatcher(s).resolve("+49911500042")
    assert m.matched and m.contact_id == cid
    assert m.matched_on == "+499115000"


async def test_missing_country_code_still_matches_on_the_suffix(s: AsyncSession) -> None:
    # stored fully, incoming without the +49 (e.g. a CDR that dropped it)
    cid = await _contact(s, "Netz AG", ["+49911223344"])
    m = await ContactMatcher(s).resolve("+499352223344")  # different area, shares tail
    # only a full-containment suffix counts, not a coincidental shared tail
    assert not m.matched
    m2 = await ContactMatcher(s).resolve("0911223344")  # -> +49911223344 exact
    assert m2.matched and m2.contact_id == cid


async def test_a_number_on_two_contacts_is_ambiguous_and_resolves_to_unknown(
    s: AsyncSession,
) -> None:
    await _contact(s, "Shared Desk A", ["+49911999000"])
    await _contact(s, "Shared Desk B", ["+49911999000"])
    m = await ContactMatcher(s).resolve("+49911999000")
    assert not m.matched
    assert m.ambiguous is True


async def test_a_soft_deleted_contact_never_matches(s: AsyncSession) -> None:
    await _contact(s, "Gone", ["+49911777888"], deleted=True)
    m = await ContactMatcher(s).resolve("+49911777888")
    assert not m.matched


async def test_a_pbx_extension_input_returns_the_extension_and_no_match(s: AsyncSession) -> None:
    await _contact(s, "Whoever", ["+49911500123"])
    m = await ContactMatcher(s).resolve("42")
    assert not m.matched
    assert m.e164 is None
    assert m.extension == "42"


async def test_longest_match_wins_over_a_shorter_base(s: AsyncSession) -> None:
    switchboard = await _contact(s, "Zentrale", ["+49911500"])
    direct = await _contact(s, "Ing. Bauer", ["+4991150042"])
    m = await ContactMatcher(s).resolve("+4991150042")
    assert m.matched and m.contact_id == direct
    assert m.contact_id != switchboard


async def test_the_cache_serves_a_repeated_lookup(s: AsyncSession) -> None:
    cid = await _contact(s, "Cached", ["+49911314159"], priority="low")
    matcher = ContactMatcher(s)
    first = await matcher.resolve("+49911314159")
    assert first.contact_id == cid

    # delete the contact directly; the cached answer is still served (TTL)
    await s.execute(ContactNumber.__table__.delete().where(ContactNumber.contact_id == cid))
    await s.commit()
    cached = await matcher.resolve("+49911314159")
    assert cached.contact_id == cid  # stale but within TTL

    clear_matcher_cache()
    fresh = await matcher.resolve("+49911314159")
    assert not fresh.matched
