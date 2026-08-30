"""bku_agents / bku_agent_enrollments / bku_agent_commands schema (E10-01)."""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.bku_agent import BkuAgent, BkuAgentCommand, BkuAgentEnrollment

_LATER = _dt.datetime(2030, 1, 1, tzinfo=_dt.UTC)


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


def _agent(workplace: uuid.UUID, status: str = "active") -> BkuAgent:
    return BkuAgent(workplace_id=workplace, device_pubkey="ssh-ed25519 AAAA", status=status)


async def test_only_one_active_agent_per_workplace(s: AsyncSession) -> None:
    wp = uuid.uuid4()
    s.add(_agent(wp))
    await s.commit()

    s.add(_agent(wp))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    # revoke the first, then a second active agent for the same workplace is fine
    q = select(BkuAgent).where(BkuAgent.workplace_id == wp)
    first = (await s.execute(q)).scalars().one()
    first.status = "revoked"
    first.revoked_at = _dt.datetime.now(_dt.UTC)
    s.add(_agent(wp))
    await s.commit()
    rows = (await s.execute(q)).scalars().all()
    assert sorted(r.status for r in rows) == ["active", "revoked"]


async def test_agent_status_is_constrained(s: AsyncSession) -> None:
    s.add(_agent(uuid.uuid4(), status="zombie"))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_generation_defaults_to_one(s: AsyncSession) -> None:
    a = _agent(uuid.uuid4())
    s.add(a)
    await s.commit()
    await s.refresh(a)
    assert a.generation == 1 and a.enrolled_at is not None


async def test_enrollment_token_hash_is_unique(s: AsyncSession) -> None:
    wp = uuid.uuid4()
    s.add(BkuAgentEnrollment(token_hash="a" * 64, workplace_id=wp, expires_at=_LATER))
    await s.commit()
    s.add(BkuAgentEnrollment(token_hash="a" * 64, workplace_id=wp, expires_at=_LATER))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_command_type_is_a_closed_set(s: AsyncSession) -> None:
    wp = uuid.uuid4()
    a = _agent(wp)
    s.add(a)
    await s.flush()
    aid = a.agent_id
    await s.commit()

    s.add(
        BkuAgentCommand(
            command_id=uuid.uuid4(),
            agent_id=aid,
            workplace_id=wp,
            type="rm -rf /",
            expires_at=_LATER,
        )
    )
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    ok = BkuAgentCommand(
        command_id=uuid.uuid4(),
        agent_id=aid,
        workplace_id=wp,
        type="restart_workstation",
        expires_at=_LATER,
    )
    s.add(ok)
    await s.commit()
    await s.refresh(ok)
    assert ok.status == "pending" and ok.payload == {}


async def test_command_cascades_when_the_agent_is_deleted(s: AsyncSession) -> None:
    wp = uuid.uuid4()
    a = _agent(wp)
    s.add(a)
    await s.flush()
    aid = a.agent_id
    s.add(
        BkuAgentCommand(
            command_id=uuid.uuid4(),
            agent_id=aid,
            workplace_id=wp,
            type="ping",
            expires_at=_LATER,
        )
    )
    await s.commit()

    a = await s.get(BkuAgent, aid)
    assert a is not None
    await s.delete(a)
    await s.commit()
    remaining = (
        (await s.execute(select(BkuAgentCommand).where(BkuAgentCommand.agent_id == aid)))
        .scalars()
        .all()
    )
    assert remaining == []
