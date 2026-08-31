"""trigger_rules / trigger_rule_versions / trigger_executions schema (E15-02)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.models.trigger_rules import (
    TriggerExecution,
    TriggerRule,
    TriggerRuleVersion,
)


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _rule(s: AsyncSession, **kw: object) -> uuid.UUID:
    r = TriggerRule(name=kw.pop("name", "BMA Halle 3"), **kw)  # type: ignore[arg-type]
    s.add(r)
    await s.flush()
    rid = r.id
    await s.commit()
    return rid


async def _version(s: AsyncSession, rule_id: uuid.UUID, **kw: object) -> uuid.UUID:
    v = TriggerRuleVersion(rule_id=rule_id, version_no=kw.pop("version_no", 1), **kw)  # type: ignore[arg-type]
    s.add(v)
    await s.flush()
    vid = v.id
    await s.commit()
    return vid


async def _inbox_event(s: AsyncSession) -> uuid.UUID:
    from bbz_core.infra.models.inbox import ProviderEventInbox

    e = ProviderEventInbox(
        provider="telephony_mock",
        dedupe_key=f"k-{uuid.uuid4().hex}",
        normalized={"event_type": "BMA_ALARM_CALL"},
    )
    s.add(e)
    await s.flush()
    eid = e.id
    await s.commit()
    return eid


async def test_defaults(s: AsyncSession) -> None:
    rid = await _rule(s)
    r = await s.get(TriggerRule, rid)
    assert r is not None and r.lifecycle == "draft" and r.priority == 100

    vid = await _version(s, rid)
    v = await s.get(TriggerRuleVersion, vid)
    assert v is not None and v.lifecycle == "draft"
    assert v.conditions == {} and v.actions == []

    eid = await _inbox_event(s)
    ex = TriggerExecution(provider_event_id=eid, rule_version_id=vid, action_index=0)
    s.add(ex)
    await s.commit()
    await s.refresh(ex)
    assert ex.status == "pending" and ex.result is None


@pytest.mark.parametrize("bad", ["active", "pending", ""])
async def test_rule_lifecycle_is_constrained(s: AsyncSession, bad: str) -> None:
    s.add(TriggerRule(name="x", lifecycle=bad))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_execution_status_is_constrained(s: AsyncSession) -> None:
    rid = await _rule(s)
    vid = await _version(s, rid)
    eid = await _inbox_event(s)
    s.add(
        TriggerExecution(
            provider_event_id=eid, rule_version_id=vid, action_index=0, status="running"
        )
    )
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_version_number_is_unique_per_rule(s: AsyncSession) -> None:
    rid = await _rule(s)
    await _version(s, rid, version_no=1)
    s.add(TriggerRuleVersion(rule_id=rid, version_no=1))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()


async def test_the_execution_key_is_exactly_once(s: AsyncSession) -> None:
    rid = await _rule(s)
    vid = await _version(s, rid)
    eid = await _inbox_event(s)
    s.add(TriggerExecution(provider_event_id=eid, rule_version_id=vid, action_index=0))
    await s.commit()

    s.add(TriggerExecution(provider_event_id=eid, rule_version_id=vid, action_index=0))
    with pytest.raises(IntegrityError):
        await s.commit()
    await s.rollback()

    # a different action index for the same event+version is fine
    s.add(TriggerExecution(provider_event_id=eid, rule_version_id=vid, action_index=1))
    await s.commit()


async def test_a_published_version_is_frozen_but_lifecycle_can_still_move(s: AsyncSession) -> None:
    rid = await _rule(s)
    vid = await _version(s, rid, lifecycle="published", conditions={"all": [{"field": "provider"}]})

    with pytest.raises(DBAPIError, match="a published version is immutable"):
        async with s.begin():
            await s.execute(
                text("UPDATE trigger_rule_versions SET conditions = '{}'::jsonb WHERE id = :i"),
                {"i": vid},
            )
    await s.rollback()

    with pytest.raises(DBAPIError, match="a published version is immutable"):
        async with s.begin():
            await s.execute(
                text(
                    'UPDATE trigger_rule_versions SET actions = \'[{"type":"notify"}]\'::jsonb '
                    "WHERE id = :i"
                ),
                {"i": vid},
            )
    await s.rollback()

    # retiring a published version (definition unchanged) is allowed
    async with s.begin():
        await s.execute(
            text("UPDATE trigger_rule_versions SET lifecycle = 'retired' WHERE id = :i"),
            {"i": vid},
        )
    lc = (
        await s.execute(select(TriggerRuleVersion.lifecycle).where(TriggerRuleVersion.id == vid))
    ).scalar_one()
    assert lc == "retired"


async def test_a_draft_version_is_freely_editable(s: AsyncSession) -> None:
    rid = await _rule(s)
    vid = await _version(s, rid, conditions={"a": 1})
    v = await s.get(TriggerRuleVersion, vid)
    assert v is not None
    v.conditions = {"b": 2}
    v.actions = [{"type": "create_event"}]
    await s.commit()

    fresh = (
        await s.execute(
            select(TriggerRuleVersion.conditions, TriggerRuleVersion.actions).where(
                TriggerRuleVersion.id == vid
            )
        )
    ).one()
    assert fresh.conditions == {"b": 2}
    assert fresh.actions == [{"type": "create_event"}]


async def test_cascades(s: AsyncSession) -> None:
    rid = await _rule(s)
    vid = await _version(s, rid)
    eid = await _inbox_event(s)
    s.add(TriggerExecution(provider_event_id=eid, rule_version_id=vid, action_index=0))
    await s.commit()

    await s.delete(await s.get(TriggerRule, rid))
    await s.commit()
    assert (await s.execute(select(TriggerRuleVersion))).scalars().all() == []
    assert (await s.execute(select(TriggerExecution))).scalars().all() == []


async def test_endpoint_binding_is_set_null_on_endpoint_delete(s: AsyncSession) -> None:
    ep = TechnicalEndpoint(name="Tür 1", type="door_station")
    s.add(ep)
    await s.flush()
    epid = ep.id
    rid = await _rule(s, endpoint_id=epid)

    await s.delete(await s.get(TechnicalEndpoint, epid))
    await s.commit()
    await s.rollback()
    endpoint_id = (
        await s.execute(select(TriggerRule.endpoint_id).where(TriggerRule.id == rid))
    ).scalar_one()
    assert endpoint_id is None
