"""Workflow engine persistence: diamond run, audit, crash recovery (E05-08)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import Event, WorkflowTemplate, WorkflowTemplateVersion
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.workflow_runtime import WorkflowToken
from bbz_core.infra.repositories.workflow_engine import (
    InstanceNotFoundError,
    StepNotAvailableError,
    WorkflowEngineService,
)

_DIAMOND: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "as", "type": "connector", "connector": "and", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "documentation"},
        {"key": "aj", "type": "connector", "connector": "and", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "as"},
        {"key": "b", "from": "as", "to": "f1"},
        {"key": "c", "from": "as", "to": "f2"},
        {"key": "d", "from": "f1", "to": "aj"},
        {"key": "e", "from": "f2", "to": "aj"},
        {"key": "f", "from": "aj", "to": "e1"},
    ],
}


async def _published(s: AsyncSession, definition: dict[str, Any]) -> tuple[uuid.UUID, uuid.UUID]:
    async with s.begin():
        ev = Event(title="Rauchmelder", priority="high")
        tpl = WorkflowTemplate(key=f"k-{uuid.uuid4().hex[:8]}", name="Ablauf")
        s.add_all([ev, tpl])
        await s.flush()
        v = WorkflowTemplateVersion(
            template_id=tpl.id, version_no=1, lifecycle="published", definition=definition
        )
        s.add(v)
        await s.flush()
        return ev.id, v.id


async def _status(s: AsyncSession, instance_id: uuid.UUID) -> str:
    return (
        await s.execute(
            text("SELECT status FROM workflow_instances WHERE id = :i"), {"i": instance_id}
        )
    ).scalar_one()


async def _audit_count(s: AsyncSession, action: str) -> int:
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_diamond_runs_to_completion_when_both_branches_finish(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _DIAMOND)
    svc = WorkflowEngineService(s)

    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)
    iid = inst.id
    # both function branches are now waiting, nothing else
    live = (
        (
            await s.execute(
                text(
                    "SELECT node_key FROM workflow_tokens "
                    "WHERE instance_id = :i AND state = 'waiting' ORDER BY node_key"
                ),
                {"i": iid},
            )
        )
        .scalars()
        .all()
    )
    assert live == ["f1", "f2"]
    assert await _status(s, iid) == "running"

    await svc.complete_step(iid, "f1", actor_id=None)
    assert await _status(s, iid) == "running"  # join still waits for f2

    await svc.complete_step(iid, "f2", result={"note": "done"})
    assert await _status(s, iid) == "completed"

    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 2
    ended = (
        await s.execute(text("SELECT ended_at FROM workflow_instances WHERE id = :i"), {"i": iid})
    ).scalar_one()
    assert ended is not None


async def test_completing_a_step_twice_is_idempotent(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _DIAMOND)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    await svc.complete_step(inst.id, "f1")
    await svc.complete_step(inst.id, "f1")  # no-op

    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 1
    n_results = (
        await s.execute(
            text("SELECT count(*) FROM workflow_task_results WHERE instance_id = :i"),
            {"i": inst.id},
        )
    ).scalar_one()
    assert n_results == 1


async def test_advance_after_a_crash_resumes_without_double_processing(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _DIAMOND)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    await svc.complete_step(inst.id, "f1")

    # a failover kicks in and blindly re-drives the instance: it must be a no-op
    await svc.advance_instance(inst.id)
    await svc.advance_instance(inst.id)
    assert await _status(s, inst.id) == "running"
    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 1

    await svc.complete_step(inst.id, "f2")
    assert await _status(s, inst.id) == "completed"

    # re-driving a finished instance leaves it alone
    await svc.advance_instance(inst.id)
    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 2


async def test_completing_a_step_that_is_not_waiting_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _DIAMOND)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    with pytest.raises(StepNotAvailableError):
        await svc.complete_step(inst.id, "aj")
    await s.rollback()


async def test_instance_must_start_on_a_published_version(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        ev = Event(title="x", priority="low")
        tpl = WorkflowTemplate(key=f"k-{uuid.uuid4().hex[:8]}", name="x")
        s.add_all([ev, tpl])
        await s.flush()
        v = WorkflowTemplateVersion(
            template_id=tpl.id, version_no=1, lifecycle="draft", definition=_DIAMOND
        )
        s.add(v)
        await s.flush()
        event_id, version_id = ev.id, v.id

    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError, match="must reference a published version"):
        await WorkflowEngineService(s).start_instance(
            event_id=event_id, template_version_id=version_id
        )
    await s.rollback()


async def test_advance_parks_a_stray_active_token_left_by_a_crash(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _DIAMOND)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    # simulate a crash that committed an active token but never processed it
    async with s.begin():
        s.add(
            WorkflowToken(instance_id=inst.id, node_key="f1", inbound_edge_key="b", state="active")
        )

    await svc.advance_instance(inst.id)
    n_active = (
        await s.execute(
            text(
                "SELECT count(*) FROM workflow_tokens WHERE instance_id = :i AND state = 'active'"
            ),
            {"i": inst.id},
        )
    ).scalar_one()
    assert n_active == 0


async def test_advancing_an_unknown_instance_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(InstanceNotFoundError):
        await WorkflowEngineService(s).advance_instance(uuid.uuid4())
    await s.rollback()


async def test_single_event_template_completes_at_once(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(
        s, {"start": "e0", "nodes": [{"key": "e0", "type": "event"}], "edges": []}
    )
    inst = await WorkflowEngineService(s).start_instance(
        event_id=event_id, template_version_id=version_id
    )
    assert await _status(s, inst.id) == "completed"
