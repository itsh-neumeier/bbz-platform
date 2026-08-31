"""Trigger-execution engine: signal → matching rules → exactly-once actions,
resumable after a crash (roadmap E15-09, MASTER_PROMPT §35)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.trigger_rules import TriggerExecution, TriggerRule, TriggerRuleVersion
from bbz_core.infra.repositories.trigger_engine import TriggerEngine, process_signal

_SIGNAL: dict[str, Any] = {
    "signal_type": "BMA_ALARM_CALL",
    "provider": "telephony_cucm",
    "occurred_at": "2026-08-31T09:00:00Z",
    "received_at": "2026-08-31T09:00:00Z",
    "gateway_node": "BBZ-SRV01",
    "source": {"dnis": "110", "severity": "critical"},
}


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _rule(
    s: AsyncSession,
    *,
    name: str,
    priority: int = 100,
    conditions: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> None:
    await s.rollback()
    async with s.begin():
        rule = TriggerRule(name=name, lifecycle="published", priority=priority)
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions=conditions or {},
                actions=actions or [{"type": "notify"}],
            )
        )


async def _count(s: AsyncSession, model: type) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def test_a_matching_rule_runs_its_actions(s: AsyncSession) -> None:
    await _rule(
        s,
        name="BMA → Ereignis",
        conditions={"op": "eq", "args": [{"field": "signal_type"}, "BMA_ALARM_CALL"]},
        actions=[{"type": "create_event", "priority": "critical"}, {"type": "notify"}],
    )

    result = await process_signal(s, signal=_SIGNAL, provider_event_id="evt-1")

    assert result.processed and result.matched_rules == 1
    assert [o.action_type for o in result.actions] == ["create_event", "notify"]
    assert await _count(s, Event) == 1
    assert await _count(s, ExternalActionOutbox) == 1


async def test_a_duplicate_provider_event_never_runs_twice(s: AsyncSession) -> None:
    """§35: duplicate provider event → no second event / no second opening."""
    await _rule(s, name="r", actions=[{"type": "create_event"}, {"type": "notify"}])

    first = await process_signal(s, signal=_SIGNAL, provider_event_id="evt-1", dedupe_key="k1")
    second = await process_signal(s, signal=_SIGNAL, provider_event_id="evt-1", dedupe_key="k1")

    assert len(first.actions) == 2
    assert second.actions == [] and second.processed
    assert await _count(s, Event) == 1
    assert await _count(s, ExternalActionOutbox) == 1
    assert await _count(s, TriggerExecution) == 2


async def test_reprocessing_an_already_processed_inbox_row_is_a_noop(s: AsyncSession) -> None:
    await _rule(s, name="r", actions=[{"type": "create_event"}])
    result = await process_signal(s, signal=_SIGNAL, provider_event_id="evt-1")

    again = await TriggerEngine(s).process_inbox_event(result.inbox_id)

    assert again.matched_rules == 0 and again.actions == []
    assert await _count(s, Event) == 1


async def test_crash_recovery_resumes_without_duplicates(s: AsyncSession) -> None:
    """Crash between the last action and mark_processed → resume, no duplicates."""
    await _rule(s, name="r", actions=[{"type": "create_event"}, {"type": "notify"}])
    result = await process_signal(s, signal=_SIGNAL, provider_event_id="evt-1")

    await s.rollback()
    async with s.begin():
        row = await s.get(ProviderEventInbox, result.inbox_id)
        assert row is not None
        row.processed_at = None  # pretend the process died before it could mark

    resumed = await TriggerEngine(s).resume_unprocessed()

    assert len(resumed) == 1 and resumed[0].actions == []  # every action already claimed
    assert await _count(s, Event) == 1
    assert await _count(s, ExternalActionOutbox) == 1
    assert await _count(s, TriggerExecution) == 2
    await s.rollback()
    assert (await s.execute(select(ProviderEventInbox.processed_at))).scalar_one() is not None


async def test_rules_fire_in_deterministic_priority_order(s: AsyncSession) -> None:
    await _rule(s, name="low-prio", priority=50, actions=[{"type": "create_event", "title": "A"}])
    await _rule(s, name="high-prio", priority=1, actions=[{"type": "create_event", "title": "B"}])

    result = await process_signal(s, signal=_SIGNAL, provider_event_id="evt-1")

    assert result.matched_rules == 2
    await s.rollback()
    title_by_id = {str(e.id): e.title for e in (await s.execute(select(Event))).scalars()}
    fired = [title_by_id[o.result["event_id"]] for o in result.actions]
    assert fired == ["B", "A"]  # priority 1 before priority 50


async def test_a_signal_matching_no_rule_is_processed_with_no_actions(s: AsyncSession) -> None:
    await _rule(
        s,
        name="only-doorbell",
        conditions={"op": "eq", "args": [{"field": "signal_type"}, "DOORBELL_RINGING"]},
    )

    result = await process_signal(s, signal=_SIGNAL, provider_event_id="evt-1")

    assert result.processed and result.matched_rules == 0 and result.actions == []
    assert await _count(s, ExternalActionOutbox) == 0


async def test_a_non_signal_inbox_row_is_skipped(s: AsyncSession) -> None:
    await _rule(s, name="r")
    await s.rollback()
    async with s.begin():
        row = ProviderEventInbox(
            provider="x",
            dedupe_key=f"k-{uuid.uuid4().hex}",
            normalized={"event_type": "CALL_RINGING"},
        )
        s.add(row)
        await s.flush()
        rid = row.id

    result = await TriggerEngine(s).process_inbox_event(rid)

    assert result.processed and result.signal_type is None and result.actions == []
    await s.rollback()
    assert (await s.execute(select(ProviderEventInbox.processed_at))).scalar_one() is not None
