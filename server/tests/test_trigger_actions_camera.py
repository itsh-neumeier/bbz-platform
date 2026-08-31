"""Camera / integration trigger actions: open_camera / open_camera_group /
integration_action enqueue one outbox row each, exactly-once, normalized handles
only, and a camera failure never blocks an earlier event (E15-07)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.triggers import validate_actions
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.models.trigger_rules import TriggerExecution, TriggerRule, TriggerRuleVersion
from bbz_core.infra.repositories.trigger_actions import TriggerActionService

_SIGNAL: dict[str, Any] = {
    "signal_type": "PANIC_ALARM_RAISED",
    "provider": "coda_video",
    "occurred_at": "2026-08-31T09:00:00Z",
    "received_at": "2026-08-31T09:00:00Z",
    "gateway_node": "BBZ-SRV01",
    "source": {"external_source_id": "CODA-ALARM-4711", "alarm_subtype": "panic_button"},
}


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _inbox_event(s: AsyncSession) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        e = ProviderEventInbox(
            provider="coda_video", dedupe_key=f"k-{uuid.uuid4().hex}", normalized=_SIGNAL
        )
        s.add(e)
        await s.flush()
        return e.id


async def _rule_version(s: AsyncSession, actions: list[dict[str, Any]]) -> TriggerRuleVersion:
    await s.rollback()
    async with s.begin():
        rule = TriggerRule(name="Coda Panik SP Nbg", lifecycle="published")
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
    result = await s.execute(
        select(ExternalActionOutbox).order_by(ExternalActionOutbox.created_at.asc())
    )
    return list(result.scalars().all())


async def _count_outbox(s: AsyncSession) -> int:
    await s.rollback()
    return (await s.execute(select(func.count()).select_from(ExternalActionOutbox))).scalar_one()


async def test_camera_actions_enqueue_one_normalized_row_each_in_order(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(
        s,
        [
            {"type": "open_camera", "camera_ref": "CAM-SP-NBG-01"},
            {"type": "open_camera_group", "camera_refs": ["CAM-SP-NBG-01", "CAM-SP-NBG-02"]},
            {
                "type": "integration_action",
                "capability": "video.focus_camera",
                "params": {"preset": "entrance"},
            },
        ],
    )

    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=_SIGNAL
    )
    assert [o.status for o in outcomes] == ["succeeded", "succeeded", "succeeded"]

    rows = await _outbox(s)
    types = [r.action_type for r in rows]
    assert types == ["open_camera", "open_camera_group", "integration_action"]
    assert rows[0].payload == {"camera_ref": "CAM-SP-NBG-01"}
    assert rows[1].payload["camera_refs"] == ["CAM-SP-NBG-01", "CAM-SP-NBG-02"]
    assert rows[2].payload == {
        "capability": "video.focus_camera",
        "params": {"preset": "entrance"},
    }
    # no vendor object id / handle leaks into the payload
    for r in rows:
        assert "camera_id" not in r.payload and "object_id" not in r.payload


async def test_camera_actions_are_exactly_once_on_replay(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(
        s,
        [
            {"type": "open_camera", "camera_ref": "CAM-1"},
            {"type": "integration_action", "capability": "video.open_alarm_context"},
        ],
    )
    svc = TriggerActionService(s)
    first = await svc.run_rule_version(provider_event_id=eid, rule_version=version, signal=_SIGNAL)
    second = await svc.run_rule_version(provider_event_id=eid, rule_version=version, signal=_SIGNAL)

    assert len(first) == 2 and second == []
    assert await _count_outbox(s) == 2
    assert (await s.execute(select(func.count()).select_from(TriggerExecution))).scalar_one() == 2


async def test_a_broken_camera_action_never_undoes_an_earlier_event(s: AsyncSession) -> None:
    eid = await _inbox_event(s)
    version = await _rule_version(
        s,
        [
            {"type": "create_event", "priority": "critical", "title": "Überfall SP Nürnberg"},
            {"type": "open_camera"},  # no camera_ref -> must fail
        ],
    )
    outcomes = await TriggerActionService(s).run_rule_version(
        provider_event_id=eid, rule_version=version, signal=_SIGNAL
    )
    assert [o.status for o in outcomes] == ["succeeded", "failed"]
    assert "camera_ref" in outcomes[1].result["error"]

    # the critical event is committed and stays; no camera outbox row was written
    await s.rollback()
    events = (await s.execute(select(Event))).scalars().all()
    assert len(events) == 1 and events[0].priority == "critical"
    assert await _count_outbox(s) == 0


def test_publish_gate_requires_the_normalized_config() -> None:
    assert validate_actions([{"type": "open_camera"}]) == [
        "action 0: open_camera requires camera_ref"
    ]
    assert validate_actions([{"type": "open_camera_group", "camera_refs": []}]) == [
        "action 0: open_camera_group requires camera_refs or camera_group_ref"
    ]
    assert validate_actions([{"type": "integration_action"}]) == [
        "action 0: integration_action requires capability"
    ]
    # well-formed actions pass
    assert (
        validate_actions(
            [
                {"type": "open_camera", "camera_ref": "CAM-1"},
                {"type": "open_camera_group", "camera_group_ref": "GRP-1"},
                {"type": "integration_action", "capability": "video.focus_camera"},
            ]
        )
        == []
    )
