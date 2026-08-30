"""Workflow engine persistence: AND / XOR / OR, audit, recovery (E05-08/09)."""

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
    DecisionNotAvailableError,
    InstanceNotFoundError,
    InvalidDecisionError,
    StepNotAvailableError,
    WorkflowEngineService,
)


def _cond(field: str, value: Any) -> dict[str, Any]:
    return {"op": "eq", "args": [{"field": field}, value]}


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


_XOR: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "manual"},
        {"key": "xj", "type": "connector", "connector": "xor", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "xs"},
        {"key": "b", "from": "xs", "to": "f1", "condition": _cond("event_priority", "critical")},
        {"key": "c", "from": "xs", "to": "f2"},
        {"key": "d", "from": "f1", "to": "xj"},
        {"key": "e", "from": "f2", "to": "xj"},
        {"key": "f", "from": "xj", "to": "e1"},
    ],
}

_XOR_NO_DEFAULT: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "manual"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "xs"},
        {"key": "b", "from": "xs", "to": "f1", "condition": _cond("status", "x")},
        {"key": "c", "from": "xs", "to": "f2", "condition": _cond("status", "y")},
    ],
}

_XOR_DEFERRED: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "f0", "type": "function", "kind": "manual"},
        {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "manual"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "f0"},
        {"key": "g", "from": "f0", "to": "xs"},
        {"key": "b", "from": "xs", "to": "f1", "condition": _cond("status", "x")},
        {"key": "c", "from": "xs", "to": "f2", "condition": _cond("status", "y")},
    ],
}

_OR: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "os", "type": "connector", "connector": "or", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "manual"},
        {"key": "oj", "type": "connector", "connector": "or", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "os"},
        {
            "key": "b",
            "from": "os",
            "to": "f1",
            "branch": "left",
            "condition": _cond("event_priority", "critical"),
        },
        {
            "key": "c",
            "from": "os",
            "to": "f2",
            "branch": "right",
            "condition": _cond("event_priority", "critical"),
        },
        {"key": "d", "from": "f1", "to": "oj"},
        {"key": "e", "from": "f2", "to": "oj"},
        {"key": "f", "from": "oj", "to": "e1"},
    ],
}


async def _published(
    s: AsyncSession, definition: dict[str, Any], *, priority: str = "high"
) -> tuple[uuid.UUID, uuid.UUID]:
    async with s.begin():
        ev = Event(title="Rauchmelder", priority=priority)
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


async def _tokens_at(s: AsyncSession, instance_id: uuid.UUID) -> list[str]:
    return list(
        (
            await s.execute(
                text(
                    "SELECT node_key FROM workflow_tokens "
                    "WHERE instance_id = :i AND state IN ('active', 'waiting') ORDER BY node_key"
                ),
                {"i": instance_id},
            )
        )
        .scalars()
        .all()
    )


async def test_xor_split_takes_exactly_one_branch_from_its_condition(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _XOR, priority="critical")
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    assert await _tokens_at(s, inst.id) == ["f1"]  # critical -> branch b only
    auto = (
        await s.execute(
            text(
                "SELECT connector_node_key, chosen_branches, auto FROM workflow_decisions "
                "WHERE instance_id = :i"
            ),
            {"i": inst.id},
        )
    ).all()
    assert auto == [("xs", ["b"], True)]
    assert await _audit_count(s, "WORKFLOW_DECISION_MADE") == 1

    await svc.complete_step(inst.id, "f1")
    assert await _status(s, inst.id) == "completed"


async def test_xor_split_without_a_match_waits_for_an_operator_decision(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _XOR_NO_DEFAULT, priority="low")
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    assert await _tokens_at(s, inst.id) == ["xs"]  # parked, no wrong path
    assert await _status(s, inst.id) == "running"

    await svc.decide(inst.id, "xs", ["c"])
    assert await _tokens_at(s, inst.id) == ["f2"]
    row = (
        await s.execute(
            text("SELECT chosen_branches, auto FROM workflow_decisions WHERE instance_id = :i"),
            {"i": inst.id},
        )
    ).one()
    assert row == (["c"], False)
    assert await _audit_count(s, "WORKFLOW_DECISION_MADE") == 1

    await svc.decide(inst.id, "xs", ["c"])  # idempotent no-op
    assert await _audit_count(s, "WORKFLOW_DECISION_MADE") == 1


async def test_or_split_multi_path_join_waits_for_the_activated_set(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _OR, priority="critical")
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    assert await _tokens_at(s, inst.id) == ["f1", "f2"]  # both guards true

    await svc.complete_step(inst.id, "f1")
    assert await _status(s, inst.id) == "running"  # OR join still waits for f2

    await svc.complete_step(inst.id, "f2")
    assert await _status(s, inst.id) == "completed"


async def test_decide_rejects_a_non_connector_and_an_unknown_branch(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _XOR_NO_DEFAULT, priority="low")
    svc = WorkflowEngineService(s)
    iid = (await svc.start_instance(event_id=event_id, template_version_id=version_id)).id

    with pytest.raises(InvalidDecisionError):
        await svc.decide(iid, "f1", ["b"])
    await s.rollback()
    with pytest.raises(InvalidDecisionError):
        await svc.decide(iid, "xs", ["nope"])
    await s.rollback()
    with pytest.raises(InvalidDecisionError):
        await svc.decide(iid, "xs", ["b", "c"])  # XOR wants exactly one
    await s.rollback()


async def test_decide_before_the_connector_is_reached_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _XOR_DEFERRED, priority="low")
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)
    # the run is parked at f0; xs has neither a token nor a decision yet
    with pytest.raises(DecisionNotAvailableError):
        await svc.decide(inst.id, "xs", ["c"])
    await s.rollback()


async def test_decide_after_an_auto_resolution_is_a_no_op(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _XOR, priority="critical")
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)
    await svc.decide(inst.id, "xs", ["c"])  # xs auto-resolved to b already -> no-op
    assert await _tokens_at(s, inst.id) == ["f1"]
    assert await _audit_count(s, "WORKFLOW_DECISION_MADE") == 1


# --- task kinds (E05-10) -----------------------------------------------------

_DOC: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "doc", "type": "function", "kind": "documentation"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "doc"},
        {"key": "b", "from": "doc", "to": "e1"},
    ],
}

_NOTIFY: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "n", "type": "function", "kind": "notification", "props": {"channel": "ops"}},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "n"},
        {"key": "b", "from": "n", "to": "e1"},
    ],
}

_ACT_THEN_MANUAL: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {
            "key": "act",
            "type": "function",
            "kind": "integration_action",
            "props": {"capability": "door.open"},
        },
        {"key": "m", "type": "function", "kind": "manual"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "act"},
        {"key": "b", "from": "act", "to": "m"},
        {"key": "c", "from": "m", "to": "e1"},
    ],
}

_TIMER: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "w", "type": "function", "kind": "timer", "props": {"duration_seconds": 1}},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "w"},
        {"key": "b", "from": "w", "to": "e1"},
    ],
}


async def _outbox(s: AsyncSession) -> list[tuple[str, str]]:
    return list(
        (
            await s.execute(
                text(
                    "SELECT action_type, dedupe_key FROM external_action_outbox ORDER BY dedupe_key"
                )
            )
        ).all()
    )


async def test_documentation_task_blocks_until_the_operator_completes_it(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _DOC)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    assert await _tokens_at(s, inst.id) == ["doc"]
    assert await _status(s, inst.id) == "running"
    assert await _outbox(s) == []

    await svc.complete_step(inst.id, "doc", result={"text": "Lage dokumentiert"})
    assert await _status(s, inst.id) == "completed"


async def test_notification_task_enqueues_exactly_one_outbox_row(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _NOTIFY)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    assert await _status(s, inst.id) == "completed"
    assert await _outbox(s) == [("notify", f"workflow-step:{inst.id}:n:attempt-0")]
    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 1


async def test_integration_task_dispatches_once_then_blocks_on_the_manual_step(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _ACT_THEN_MANUAL)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    assert await _tokens_at(s, inst.id) == ["m"]  # integration done, parked on manual
    assert await _outbox(s) == [("integration", f"workflow-step:{inst.id}:act:attempt-0")]

    # a blind re-drive (failover) must not enqueue the action a second time
    await svc.advance_instance(inst.id)
    assert len(await _outbox(s)) == 1

    await svc.complete_step(inst.id, "m")
    assert await _status(s, inst.id) == "completed"
    assert len(await _outbox(s)) == 1


async def test_timer_task_fires_after_its_deadline_across_a_restart(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published(s, _TIMER)
    svc = WorkflowEngineService(s)
    inst = await svc.start_instance(event_id=event_id, template_version_id=version_id)

    assert await _tokens_at(s, inst.id) == ["w"]
    resume_at = (
        await s.execute(
            text("SELECT resume_at FROM workflow_tokens WHERE instance_id = :i AND node_key = 'w'"),
            {"i": inst.id},
        )
    ).scalar_one()
    assert resume_at is not None

    # nothing is due yet
    assert await WorkflowEngineService(s).fire_due_timers() == 0
    assert await _status(s, inst.id) == "running"

    # simulate the deadline passing (and a restart in between)
    await s.execute(
        text(
            "UPDATE workflow_tokens SET resume_at = now() - interval '1 minute' "
            "WHERE instance_id = :i AND node_key = 'w'"
        ),
        {"i": inst.id},
    )
    await s.commit()
    assert await WorkflowEngineService(s).fire_due_timers() == 1
    assert await _status(s, inst.id) == "completed"
    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 1
    # a second sweep has nothing to do
    assert await WorkflowEngineService(s).fire_due_timers() == 0


async def test_fire_due_timers_skips_stale_and_finished_rows(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    svc = WorkflowEngineService(s)
    ev1, ver1 = await _published(s, _TIMER)
    i1 = (await svc.start_instance(event_id=ev1, template_version_id=ver1)).id
    ev2, ver2 = await _published(s, _TIMER)
    i2 = (await svc.start_instance(event_id=ev2, template_version_id=ver2)).id

    # i1: a due timer on an already-completed step -> skipped (idempotent)
    await s.execute(
        text(
            "INSERT INTO workflow_task_results (instance_id, node_key, result) "
            "VALUES (:i, 'w', '{}'::jsonb)"
        ),
        {"i": i1},
    )
    # i2: a due timer on a cancelled instance -> skipped
    await s.execute(
        text("UPDATE workflow_instances SET status = 'cancelled' WHERE id = :i"), {"i": i2}
    )
    await s.execute(
        text(
            "UPDATE workflow_tokens SET resume_at = now() - interval '1 min' "
            "WHERE instance_id IN (:a, :b) AND node_key = 'w'"
        ),
        {"a": i1, "b": i2},
    )
    await s.commit()

    assert await WorkflowEngineService(s).fire_due_timers() == 0
    assert await _status(s, i1) == "running"
