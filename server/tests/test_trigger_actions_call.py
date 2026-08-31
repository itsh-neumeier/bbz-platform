"""Telephony trigger actions: answer_call / send_dtmf_profile / hangup_call
enqueue one outbox row each, exactly-once, no DTMF code (E15-08)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.trigger_rules import TriggerExecution, TriggerRule, TriggerRuleVersion
from bbz_core.infra.repositories.trigger_actions import TriggerActionService

_SIGNAL: dict[str, Any] = {
    "signal_type": "DOORBELL_RINGING",
    "provider": "telephony_mock",
    "occurred_at": "2026-08-31T09:00:00Z",
    "received_at": "2026-08-31T09:00:00Z",
    "gateway_node": "BBZ-SRV01",
    "source": {"source_call_id": "call-siedle-1", "dnis": "200"},
}


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _inbox_event(s: AsyncSession) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        e = ProviderEventInbox(
            provider="telephony_mock", dedupe_key=f"k-{uuid.uuid4().hex}", normalized=_SIGNAL
        )
        s.add(e)
        await s.flush()
        return e.id


async def _rule_version(s: AsyncSession, actions: list[dict[str, Any]]) -> TriggerRuleVersion:
    await s.rollback()
    async with s.begin():
        rule = TriggerRule(name="Siedle Tür", lifecycle="published")
        s.add(rule)
        await s.flush()
        v = TriggerRuleVersion(
            rule_id=rule.id, version_no=1, lifecycle="published", conditions={}, actions=actions
        )
        s.add(v)
        await s.flush()
        await s.refresh(v)
        s.expunge(v)
        return v


async def _outbox(s: AsyncSession) -> list[ExternalActionOutbox]:
    await s.rollback()
    return list(
        (
            await s.execute(
                select(ExternalActionOutbox).order_by(ExternalActionOutbox.created_at.asc())
            )
        )
        .scalars()
        .all()
    )


async def test_answer_dtmf_hangup_enqueues_one_row_each_in_order(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(
        s,
        [
            {"type": "answer_call"},
            {"type": "send_dtmf_profile", "dtmf_profile_id": "siedle_haupttor"},
            {"type": "hangup_call"},
        ],
    )

    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=_SIGNAL
    )
    assert [o.status for o in outcomes] == ["succeeded", "succeeded", "succeeded"]

    rows = await _outbox(s)
    assert [r.action_type for r in rows] == ["answer_call", "send_dtmf_profile", "hangup_call"]
    for r in rows:
        assert r.payload["call_id"] == "call-siedle-1"
    assert rows[1].payload["dtmf_profile_id"] == "siedle_haupttor"


async def test_the_dtmf_code_never_appears_in_the_payload_or_audit(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(
        s, [{"type": "send_dtmf_profile", "dtmf_profile_id": "gate", "code": "1234#"}]
    )
    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=_SIGNAL
    )
    # a code in the action config is rejected outright
    assert outcomes[0].status == "failed"
    assert await _count_outbox(s) == 0

    # a clean profile-only action: no "code"/"dtmf" anywhere
    eid2 = await _inbox_event(s)
    v2 = await _rule_version(s, [{"type": "send_dtmf_profile", "dtmf_profile_id": "gate"}])
    await TriggerActionService(s).run_rule_version(
        provider_event_id=eid2, rule_version=v2, signal=_SIGNAL
    )
    await s.rollback()
    outbox = (await s.execute(select(ExternalActionOutbox))).scalars().one()
    assert "code" not in outbox.payload and "dtmf" not in outbox.payload
    audits = (
        (await s.execute(select(AuditEvent).where(AuditEvent.action == "TRIGGER_EXECUTED")))
        .scalars()
        .all()
    )
    for a in audits:
        assert "1234" not in str(a.after)


async def test_call_actions_are_exactly_once_on_replay(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(
        s,
        [
            {"type": "answer_call"},
            {"type": "send_dtmf_profile", "dtmf_profile_id": "gate"},
            {"type": "hangup_call"},
        ],
    )
    svc = TriggerActionService(s)
    first = await svc.run_rule_version(provider_event_id=eid, rule_version=version, signal=_SIGNAL)
    second = await svc.run_rule_version(provider_event_id=eid, rule_version=version, signal=_SIGNAL)

    assert len(first) == 3 and second == []
    assert await _count_outbox(s) == 3
    assert (await s.execute(select(func.count()).select_from(TriggerExecution))).scalar_one() == 3


async def test_a_call_action_without_a_call_id_fails(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(s, [{"type": "answer_call"}])
    no_call_signal = {**_SIGNAL, "source": {"dnis": "200"}}
    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=no_call_signal
    )
    assert outcomes[0].status == "failed"
    assert "call_id" in outcomes[0].result["error"]


async def _count_outbox(s: AsyncSession) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(ExternalActionOutbox))).scalar_one()
