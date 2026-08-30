"""workflow_templates / workflow_template_versions schema + immutability (E05-03)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models import (
    Base,
    WorkflowLifecycle,
    WorkflowTemplate,
    WorkflowTemplateVersion,
)


def test_tables_and_constraints_registered() -> None:
    assert {"workflow_templates", "workflow_template_versions"} <= set(Base.metadata.tables)
    uqs = {
        c.name
        for c in WorkflowTemplateVersion.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    }
    assert "uq_wtv_template_version" in uqs


async def _template_with_version(
    s: AsyncSession, *, lifecycle: WorkflowLifecycle, definition: dict[str, object]
) -> tuple[uuid.UUID, uuid.UUID]:
    """Returns (template_id, version_id)."""
    async with s.begin():
        tpl = WorkflowTemplate(key=f"k-{uuid.uuid4().hex[:8]}", name="Rauchmelder-Ablauf")
        s.add(tpl)
        await s.flush()
        v = WorkflowTemplateVersion(
            template_id=tpl.id,
            version_no=1,
            lifecycle=lifecycle.value,
            definition=definition,
        )
        s.add(v)
        await s.flush()
        ids = (tpl.id, v.id)
    return ids


async def test_version_roundtrip_and_unique_version_no(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    template_id, _ = await _template_with_version(
        s, lifecycle=WorkflowLifecycle.DRAFT, definition={"nodes": []}
    )
    async with s.begin():
        s.add(
            WorkflowTemplateVersion(
                template_id=template_id, version_no=1, lifecycle="draft", definition={}
            )
        )
        with pytest.raises(IntegrityError):
            await s.flush()


async def test_draft_definition_can_be_edited(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    _, vid = await _template_with_version(
        s, lifecycle=WorkflowLifecycle.DRAFT, definition={"nodes": []}
    )
    async with s.begin():
        await s.execute(
            text(
                "UPDATE workflow_template_versions SET definition = '{\"nodes\":[1]}'::jsonb "
                "WHERE id = :i"
            ),
            {"i": vid},
        )
    got = (
        await s.execute(
            text("SELECT definition FROM workflow_template_versions WHERE id = :i"), {"i": vid}
        )
    ).scalar_one()
    assert got == {"nodes": [1]}


async def test_published_definition_is_frozen_but_lifecycle_can_move(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    _, vid = await _template_with_version(
        s, lifecycle=WorkflowLifecycle.PUBLISHED, definition={"nodes": ["a"]}
    )

    with pytest.raises(DBAPIError, match="published definition is immutable"):
        async with s.begin():
            await s.execute(
                text(
                    "UPDATE workflow_template_versions SET definition = '{}'::jsonb WHERE id = :i"
                ),
                {"i": vid},
            )
    await s.rollback()

    # deprecating a published version is still allowed (definition unchanged)
    async with s.begin():
        await s.execute(
            text("UPDATE workflow_template_versions SET lifecycle = 'deprecated' WHERE id = :i"),
            {"i": vid},
        )
    lc = (
        await s.execute(
            text("SELECT lifecycle FROM workflow_template_versions WHERE id = :i"), {"i": vid}
        )
    ).scalar_one()
    assert lc == "deprecated"


async def test_bad_lifecycle_value_is_rejected(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        tpl = WorkflowTemplate(key=f"k-{uuid.uuid4().hex[:8]}", name="x")
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="bogus", definition={}
            )
        )
        with pytest.raises(IntegrityError):
            await s.flush()
