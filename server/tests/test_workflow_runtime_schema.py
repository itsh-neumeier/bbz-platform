"""Workflow runtime schema: FK constraints + published-version guard (E05-05)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import (
    Base,
    Event,
    WorkflowInstance,
    WorkflowTemplate,
    WorkflowTemplateVersion,
    WorkflowToken,
)


def test_runtime_tables_registered() -> None:
    assert {
        "workflow_instances",
        "workflow_tokens",
        "workflow_task_results",
        "workflow_decisions",
    } <= set(Base.metadata.tables)


async def _published_version(s: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (event_id, published_template_version_id)."""
    async with s.begin():
        ev = Event(title="Rauchmelder", priority="high")
        tpl = WorkflowTemplate(key=f"k-{uuid.uuid4().hex[:8]}", name="Ablauf")
        s.add_all([ev, tpl])
        await s.flush()
        v = WorkflowTemplateVersion(
            template_id=tpl.id,
            version_no=1,
            lifecycle="published",
            definition={"start": "n", "nodes": [], "edges": []},
        )
        s.add(v)
        await s.flush()
        ids = (ev.id, v.id)
    return ids


async def test_instance_on_published_version_is_allowed(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published_version(s)
    async with s.begin():
        inst = WorkflowInstance(event_id=event_id, template_version_id=version_id)
        s.add(inst)
        await s.flush()
        iid = inst.id
    async with s.begin():
        s.add(WorkflowToken(instance_id=iid, node_key="n"))
    got = (
        await s.execute(
            text("SELECT count(*) FROM workflow_tokens WHERE instance_id = :i"), {"i": iid}
        )
    ).scalar_one()
    assert got == 1


async def test_instance_on_draft_version_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        ev = Event(title="x", priority="low")
        tpl = WorkflowTemplate(key=f"k-{uuid.uuid4().hex[:8]}", name="x")
        s.add_all([ev, tpl])
        await s.flush()
        v = WorkflowTemplateVersion(
            template_id=tpl.id, version_no=1, lifecycle="draft", definition={}
        )
        s.add(v)
        await s.flush()
        event_id, version_id = ev.id, v.id

    with pytest.raises(DBAPIError, match="must reference a published version"):
        async with s.begin():
            s.add(WorkflowInstance(event_id=event_id, template_version_id=version_id))
            await s.flush()
    await s.rollback()


async def test_token_needs_a_real_instance(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(IntegrityError):
        async with s.begin():
            s.add(WorkflowToken(instance_id=uuid.uuid4(), node_key="n"))
            await s.flush()
    await s.rollback()


async def test_one_event_may_have_several_instances(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    event_id, version_id = await _published_version(s)
    async with s.begin():
        s.add_all(
            [
                WorkflowInstance(event_id=event_id, template_version_id=version_id),
                WorkflowInstance(event_id=event_id, template_version_id=version_id),
            ]
        )
    n = (
        await s.execute(
            text("SELECT count(*) FROM workflow_instances WHERE event_id = :e"), {"e": event_id}
        )
    ).scalar_one()
    assert n == 2
