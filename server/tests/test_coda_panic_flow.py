"""§36.1 Coda panic/duress runtime flow (roadmap E16-07): a Coda panic alarm
raises exactly one critical event with the published EPK version bound, a client
popup and the priority warning; the camera group is a decoupled outbox side
effect; a duplicate alarm raises no second event.

Proves E16-04 -> E15-09 -> E15-06/07 compose. New code: ``from_incoming_alarm``
and ``alarm_ingest._queue_signal``.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.alarm_ingest import ingest_alarm_event
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.client_popup_events import ClientPopupEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.technical_endpoints import TechnicalEndpoint
from bbz_core.infra.models.trigger_rules import TriggerRule, TriggerRuleVersion
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.models.workflow_runtime import WorkflowInstance
from bbz_core.infra.repositories.trigger_engine import TriggerEngine

_SOURCE = "CODA-ALARM-4711"
_WORKPLACE = "11111111-1111-1111-1111-111111111111"
_GRAPH: dict[str, Any] = {
    "start": "e0",
    "nodes": [{"key": "e0", "type": "event"}, {"key": "e1", "type": "event"}],
    "edges": [{"key": "a", "from": "e0", "to": "e1"}],
}


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


def _panic_alarm(event_id: str = "CODA-EVT-1") -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    return {
        "provider": "coda_video",
        "provider_instance_id": "coda-mock-1",
        "provider_event_id": event_id,
        "alarm_type": "panic",
        "alarm_subtype": "panic_button",
        "source_external_id": _SOURCE,
        "source_name": "Ueberfalltaster ServicePoint Nuernberg Hbf",
        "site_external_id": "Nuernberg Hbf",
        "occurred_at": now,
        "received_at": now,
        "severity_external": "critical",
        "associated_camera_ids": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"],
        "raw": {"id": event_id, "src": _SOURCE},
    }


async def _seed(s: AsyncSession) -> uuid.UUID:
    """Coda endpoint + workflow (v1 deprecated, v2 published) + a published rule
    matching the panic source. Returns the current published version id (v2)."""
    await s.rollback()
    async with s.begin():
        endpoint = TechnicalEndpoint(
            name="Ueberfalltaster SP Nbg",
            type="panic_button",
            site="Nuernberg Hbf",
            provider_id="coda_video",
            external_source_ids=[_SOURCE],
            default_priority="critical",
        )
        s.add(endpoint)
        await s.flush()

        tpl = WorkflowTemplate(key="ueberfall", name="Ueberfall ServicePoint")
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="deprecated", definition=_GRAPH
            )
        )
        v2 = WorkflowTemplateVersion(
            template_id=tpl.id, version_no=2, lifecycle="published", definition=_GRAPH
        )
        s.add(v2)

        rule = TriggerRule(
            name="Coda Panik SP Nbg -> kritisches Ereignis + EPK + Popup",
            endpoint_id=endpoint.id,
            lifecycle="published",
            priority=1,
        )
        s.add(rule)
        await s.flush()
        s.add(
            TriggerRuleVersion(
                rule_id=rule.id,
                version_no=1,
                lifecycle="published",
                conditions={"op": "eq", "args": [{"field": "external_source_id"}, _SOURCE]},
                actions=[
                    {
                        "type": "create_event",
                        "priority": "critical",
                        "title": "Ueberfall SP Nuernberg",
                    },
                    {"type": "attach_workflow", "template_key": "ueberfall"},
                    {"type": "show_client_popup", "workplace_id": _WORKPLACE, "kind": "panic"},
                    {
                        "type": "open_camera_group",
                        "camera_refs": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"],
                    },
                ],
            )
        )
        await s.flush()
        return v2.id


async def _count(s: AsyncSession, model: type) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(model))).scalar_one()


async def _drain(s: AsyncSession) -> None:
    await s.rollback()
    await TriggerEngine(s).resume_unprocessed()


async def test_a_coda_panic_alarm_runs_the_full_36_1_flow(s: AsyncSession) -> None:
    wf_v2 = await _seed(s)

    async with s.begin():
        result = await ingest_alarm_event(s, _panic_alarm())
    assert result.outcome.value == "new"
    await _drain(s)

    # exactly one critical event, from the trigger, still 'new'
    event = (await s.execute(select(Event))).scalars().one()
    assert event.priority == "critical"
    assert event.status == "new"
    assert event.source == "trigger"
    assert event.title == "Ueberfall SP Nuernberg"

    # the current published EPK version is bound
    instance = (await s.execute(select(WorkflowInstance))).scalars().one()
    assert instance.event_id == event.id and instance.template_version_id == wf_v2

    # operator popup raised (row + append-only domain event)
    popup = (await s.execute(select(ClientPopupEvent))).scalars().one()
    assert str(popup.workplace_id) == _WORKPLACE
    raised = (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "CLIENT_POPUP_RAISED")
        )
    ).scalar_one()
    assert raised == 1

    # the camera group is a decoupled outbox side effect (normalized handles only)
    cam = (
        (
            await s.execute(
                select(ExternalActionOutbox).where(
                    ExternalActionOutbox.action_type == "open_camera_group"
                )
            )
        )
        .scalars()
        .one()
    )
    assert cam.payload["camera_refs"] == ["CAM-SP-NBG-01", "CAM-SP-NBG-02"]
    assert "camera_id" not in cam.payload

    # all 4 trigger actions audited
    audited = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "TRIGGER_EXECUTED")
        )
    ).scalar_one()
    assert audited == 4

    # the immutable provider alarm event + its queued signal row are both present
    inbox = (await s.execute(select(ProviderEventInbox))).scalars().all()
    assert sorted(r.dedupe_key.split(":")[0] for r in inbox) == ["coda_video", "signal"]
    alarm_row = next(r for r in inbox if not r.dedupe_key.startswith("signal:"))
    assert alarm_row.normalized["raw_hash"] == alarm_row.raw_hash
    assert "raw" not in alarm_row.normalized
    assert all(r.processed_at is not None for r in inbox)


async def test_a_duplicate_coda_panic_alarm_creates_no_second_event(s: AsyncSession) -> None:
    await _seed(s)

    async with s.begin():
        first = await ingest_alarm_event(s, _panic_alarm("CODA-EVT-1"))
    await _drain(s)
    async with s.begin():
        second = await ingest_alarm_event(s, _panic_alarm("CODA-EVT-1"))  # replay / failover
    await _drain(s)

    assert first.outcome.value == "new" and second.outcome.value == "duplicate"
    assert await _count(s, Event) == 1
    assert await _count(s, WorkflowInstance) == 1
    assert await _count(s, ClientPopupEvent) == 1
    assert (
        await s.execute(
            select(func.count())
            .select_from(ExternalActionOutbox)
            .where(ExternalActionOutbox.action_type == "open_camera_group")
        )
    ).scalar_one() == 1


async def test_an_alarm_from_an_unconfigured_source_creates_no_event(s: AsyncSession) -> None:
    await _seed(s)
    async with s.begin():
        await ingest_alarm_event(s, {**_panic_alarm("X-1"), "source_external_id": "OTHER"})
    await _drain(s)
    assert await _count(s, Event) == 0
    assert await _count(s, WorkflowInstance) == 0
