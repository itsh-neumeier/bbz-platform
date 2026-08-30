"""Workflow (EPK-style handling-instruction) templates and their versions.

`.ai/WORKFLOW_EPK.md`: a template has a lifecycle DRAFT -> VALIDATED ->
PUBLISHED -> DEPRECATED; ADR-0005: a **published** version is immutable — a
running instance pinned to v3 must never be changed by publishing v4.

``definition`` is a versioned structured graph (JSON Schema
``workflow.graph.v1``); ``workflow_graph_nodes`` / ``workflow_graph_edges`` are
**derived** index tables, rebuilt deterministically from it (E05-04). Publish
validation and the runtime land in E05-06 ff.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid
from typing import Any

from sqlalchemy import (
    DDL,
    CheckConstraint,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class WorkflowLifecycle(enum.StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id: Mapped[uuid.UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))


class WorkflowTemplateVersion(Base):
    __tablename__ = "workflow_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version_no", name="uq_wtv_template_version"),
        CheckConstraint(
            "lifecycle IN ('draft', 'validated', 'published', 'deprecated')",
            name="lifecycle",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_templates.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    lifecycle: Mapped[str] = mapped_column(
        String(16), server_default=WorkflowLifecycle.DRAFT.value, index=True
    )
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    changelog: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    published_at: Mapped[_dt.datetime | None] = mapped_column()
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class WorkflowGraphNode(Base):
    """Derived index of one node in a template version's graph (E05-04)."""

    __tablename__ = "workflow_graph_nodes"
    __table_args__ = (
        UniqueConstraint("template_version_id", "node_key", name="uq_wgn_version_key"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_template_versions.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64))
    node_type: Mapped[str] = mapped_column(String(16))  # event | function | connector
    function_kind: Mapped[str | None] = mapped_column(String(32))
    connector_type: Mapped[str | None] = mapped_column(String(8))  # and | or | xor
    connector_direction: Mapped[str | None] = mapped_column(String(8))  # split | join
    label: Mapped[str | None] = mapped_column(String(300))
    props: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class WorkflowGraphEdge(Base):
    """Derived index of one edge in a template version's graph (E05-04)."""

    __tablename__ = "workflow_graph_edges"
    __table_args__ = (
        UniqueConstraint("template_version_id", "edge_key", name="uq_wge_version_key"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_template_versions.id", ondelete="CASCADE"), index=True
    )
    edge_key: Mapped[str] = mapped_column(String(64))
    from_node_key: Mapped[str] = mapped_column(String(64), index=True)
    to_node_key: Mapped[str] = mapped_column(String(64), index=True)
    branch_label: Mapped[str | None] = mapped_column(String(64))
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


# ADR-0005: once published, the definition is frozen. The migration
# 0017_workflow_templates creates the same guard for provisioned databases.
_FROZEN_FN = "bbz_forbid_published_definition_change"
_FROZEN_FN_DDL = DDL(  # type: ignore[no-untyped-call]
    f"CREATE OR REPLACE FUNCTION {_FROZEN_FN}() RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN "
    "IF OLD.lifecycle = 'published' AND NEW.definition IS DISTINCT FROM OLD.definition THEN "
    "RAISE EXCEPTION 'workflow_template_versions: a published definition is immutable'; "
    "END IF; RETURN NEW; END; $$"
)
_FROZEN_TRIGGER_DDL = DDL(  # type: ignore[no-untyped-call]
    "CREATE TRIGGER workflow_template_versions_freeze_published BEFORE UPDATE "
    f"ON workflow_template_versions FOR EACH ROW EXECUTE FUNCTION {_FROZEN_FN}()"
)
event.listen(
    WorkflowTemplateVersion.__table__,
    "after_create",
    _FROZEN_FN_DDL.execute_if(dialect="postgresql"),
)
event.listen(
    WorkflowTemplateVersion.__table__,
    "after_create",
    _FROZEN_TRIGGER_DDL.execute_if(dialect="postgresql"),
)
