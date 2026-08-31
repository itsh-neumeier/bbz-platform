"""Typed trigger actions: create_event / attach_workflow / show_client_popup /
notify — one effect each, exactly-once on replay (E15-06)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.client_popup_events import ClientPopupEvent
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.trigger_rules import (
    TriggerExecution,
    TriggerRule,
    TriggerRuleVersion,
)
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import WorkflowInstance
from bbz_core.infra.repositories.trigger_actions import TriggerActionService

_GRAPH: dict[str, Any] = {
    "start": "e0",
    "nodes": [{"key": "e0", "type": "event"}, {"key": "e1", "type": "event"}],
    "edges": [{"key": "a", "from": "e0", "to": "e1"}],
}

_SIGNAL = {
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


async def _published_template(s: AsyncSession, key: str) -> None:
    async with s.begin():
        tpl = WorkflowTemplate(key=key, name=key)
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="published", definition=_GRAPH
            )
        )


async def _inbox_event(s: AsyncSession) -> uuid.UUID:
    async with s.begin():
        e = ProviderEventInbox(
            provider="telephony_cucm",
            dedupe_key=f"k-{uuid.uuid4().hex}",
            normalized=_SIGNAL,
        )
        s.add(e)
        await s.flush()
        return e.id


async def _rule_version(s: AsyncSession, actions: list[dict[str, Any]]) -> TriggerRuleVersion:
    async with s.begin():
        rule = TriggerRule(name="BMA → Ereignis + Workflow + Popup", lifecycle="published")
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


async def _count(s: AsyncSession, model: type) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def test_a_rule_fires_one_event_one_workflow_one_popup_one_notify(s: AsyncSession) -> None:
    await _published_template(s, "bma_alarm")
    eid = await _inbox_event(s)
    workplace = uuid.uuid4()
    version = await _rule_version(
        s,
        [
            {"type": "create_event", "priority": "critical", "title": "BMA Halle 3"},
            {"type": "attach_workflow", "template_key": "bma_alarm"},
            {
                "type": "show_client_popup",
                "workplace_id": str(workplace),
                "kind": "technical_alarm",
            },
            {"type": "notify", "payload": {"channel": "leitstelle"}},
        ],
    )

    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=_SIGNAL
    )
    assert [o.status for o in outcomes] == ["succeeded"] * 4

    assert await _count(s, Event) == 1
    assert await _count(s, WorkflowInstance) == 1
    assert await _count(s, ClientPopupEvent) == 1
    assert await _count(s, ExternalActionOutbox) == 1
    assert await _count(s, TriggerExecution) == 4
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "TRIGGER_EXECUTED")
        )
    ).scalar_one() == 4

    await s.rollback()
    ev = (await s.execute(select(Event))).scalars().one()
    assert ev.title == "BMA Halle 3" and ev.priority == "critical" and ev.source == "trigger"
    popup = (await s.execute(select(ClientPopupEvent))).scalars().one()
    assert popup.workplace_id == workplace and popup.kind == "technical_alarm"
    outbox = (await s.execute(select(ExternalActionOutbox))).scalars().one()
    assert outbox.action_type == "notify"


async def test_replaying_the_same_signal_produces_no_duplicates(s: AsyncSession) -> None:
    await _published_template(s, "bma_alarm")
    eid = await _inbox_event(s)
    version = await _rule_version(
        s,
        [
            {"type": "create_event", "priority": "high"},
            {"type": "attach_workflow", "template_key": "bma_alarm"},
            {"type": "notify"},
        ],
    )
    svc = TriggerActionService(s)

    first = await svc.run_rule_version(provider_event_id=eid, rule_version=version, signal=_SIGNAL)
    second = await svc.run_rule_version(provider_event_id=eid, rule_version=version, signal=_SIGNAL)

    assert len(first) == 3
    assert second == []  # every action already claimed
    assert await _count(s, Event) == 1
    assert await _count(s, WorkflowInstance) == 1
    assert await _count(s, ExternalActionOutbox) == 1
    assert await _count(s, TriggerExecution) == 3


async def test_a_failing_action_is_recorded_and_does_not_undo_earlier_ones(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(
        s,
        [
            {"type": "create_event", "priority": "high"},
            {"type": "attach_workflow", "template_key": "does_not_exist"},
        ],
    )

    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=_SIGNAL
    )
    assert [o.status for o in outcomes] == ["succeeded", "failed"]

    assert await _count(s, Event) == 1  # the create_event stuck
    assert await _count(s, WorkflowInstance) == 0
    await s.rollback()
    rows = (
        (await s.execute(select(TriggerExecution).order_by(TriggerExecution.action_index)))
        .scalars()
        .all()
    )
    assert [r.status for r in rows] == ["succeeded", "failed"]
    assert "does_not_exist" in rows[1].result["error"]


async def test_an_unknown_action_type_fails_that_action_only(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(s, [{"type": "create_event"}, {"type": "open_the_pod_bay_doors"}])
    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=_SIGNAL
    )
    assert [o.status for o in outcomes] == ["succeeded", "failed"]
    assert await _count(s, Event) == 1
