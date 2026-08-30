"""lines / calls / call_participants / call_documentation schema (E11-01)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.telephony import (
    Call,
    CallDocumentation,
    CallParticipant,
    Line,
)


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


def _call(**kw: object) -> Call:
    base: dict[str, object] = {
        "bbz_call_id": f"CALL-{uuid.uuid4().hex[:8]}",
        "provider": "telephony_mock",
        "direction": "inbound",
    }
    base.update(kw)
    return Call(**base)  # type: ignore[arg-type]


async def test_bbz_call_id_is_unique_and_independent_of_source(s: AsyncSession) -> None:
    a = _call(bbz_call_id="CALL-1", source_call_id="prov-xyz")
    b = _call(bbz_call_id="CALL-2", source_call_id="prov-xyz")  # same provider id, different call
    s.add_all([a, b])
    await s.commit()  # a provider id is not unique — two calls may share one

    s.add(_call(bbz_call_id="CALL-1"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_call_defaults(s: AsyncSession) -> None:
    c = _call()
    s.add(c)
    await s.commit()
    await s.refresh(c)
    assert c.state == "offered"
    assert c.source_call_id is None
    assert c.created_at is not None


@pytest.mark.parametrize("bad_col,bad_val", [("direction", "sideways"), ("state", "levitating")])
async def test_call_enums_are_constrained(s: AsyncSession, bad_col: str, bad_val: str) -> None:
    s.add(_call(**{bad_col: bad_val}))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_line_provider_external_id_is_unique(s: AsyncSession) -> None:
    s.add(Line(provider="cucm", external_id="SEP001", label="Platz 1"))
    await s.commit()
    s.add(Line(provider="cucm", external_id="SEP001"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()
    # a different provider may reuse the external id
    s.add(Line(provider="telephony_mock", external_id="SEP001"))
    await s.commit()


async def test_participant_role_is_constrained(s: AsyncSession) -> None:
    c = _call()
    s.add(c)
    await s.flush()
    cid = c.id
    await s.commit()

    s.add(CallParticipant(call_id=cid, role="bystander"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    s.add(CallParticipant(call_id=cid, number="+49911500", display_name="EVU", role="caller"))
    await s.commit()


async def test_participant_cascades_when_the_call_is_deleted(s: AsyncSession) -> None:
    c = _call()
    s.add(c)
    await s.flush()
    cid = c.id
    s.add(CallParticipant(call_id=cid, role="caller"))
    await s.commit()

    await s.delete(await s.get(Call, cid))
    await s.commit()
    left = (
        (await s.execute(select(CallParticipant).where(CallParticipant.call_id == cid)))
        .scalars()
        .all()
    )
    assert left == []


async def test_call_documentation_category_may_be_null_then_a_valid_enum(s: AsyncSession) -> None:
    c = _call()
    s.add(c)
    await s.flush()
    cid = c.id
    s.add(CallDocumentation(call_id=cid))  # category not set yet
    await s.commit()

    doc = await s.get(CallDocumentation, cid)
    assert doc is not None and doc.category is None and doc.mandatory_done is False

    doc.category = "gossip"
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    doc = await s.get(CallDocumentation, cid)
    assert doc is not None
    doc.category = "technical_fault"
    doc.mandatory_done = True
    await s.commit()
    await s.refresh(doc)
    assert doc.category == "technical_fault"


async def test_only_one_documentation_row_per_call(s: AsyncSession) -> None:
    c = _call()
    s.add(c)
    await s.flush()
    cid = c.id
    s.add(CallDocumentation(call_id=cid))
    await s.commit()
    s.expunge_all()

    s.add(CallDocumentation(call_id=cid))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()
