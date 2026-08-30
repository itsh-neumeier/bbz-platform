"""Workflow engine runtime tables (roadmap E05-05, `.ai/WORKFLOW_EPK.md`).

An instance is pinned to an **immutable published** template version (a
``BEFORE INSERT`` trigger enforces the PUBLISHED requirement, since a FK cannot).
One event may have several workflow instances — that is allowed policy, so there
is no unique constraint on ``event_id``.

Schema only. The engine (token flow, split/join, task completion, decisions) is
E05-07 ff.
"""

from __future__ import annotations

import datetime as _dt
import enum
import uuid
from typing import Any

from sqlalchemy import (
    DDL,
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bbz_core.infra.models.base import Base, uuid_pk


class WorkflowInstanceStatus(enum.StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class WorkflowTokenState(enum.StrEnum):
    ACTIVE = "active"
    WAITING = "waiting"
    CONSUMED = "consumed"


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'cancelled', 'failed')", name="status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_template_versions.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), server_default=WorkflowInstanceStatus.RUNNING.value, index=True
    )
    started_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    ended_at: Mapped[_dt.datetime | None] = mapped_column()


class WorkflowToken(Base):
    __tablename__ = "workflow_tokens"
    __table_args__ = (CheckConstraint("state IN ('active', 'waiting', 'consumed')", name="state"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64), index=True)
    #: key of the edge the token arrived on (``None`` for the seed token). Lets
    #: an AND join tell its incoming branches apart (E05-08).
    inbound_edge_key: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(16), server_default=WorkflowTokenState.ACTIVE.value)
    #: when a parked ``timer`` task is due to resume (persisted so it still
    #: fires after a server restart, E05-10).
    resume_at: Mapped[_dt.datetime | None] = mapped_column(index=True)
    entered_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    left_at: Mapped[_dt.datetime | None] = mapped_column()


class WorkflowTaskResult(Base):
    __tablename__ = "workflow_task_results"

    id: Mapped[uuid.UUID] = uuid_pk()
    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64), index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))


class WorkflowDecision(Base):
    __tablename__ = "workflow_decisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    connector_node_key: Mapped[str] = mapped_column(String(64), index=True)
    chosen_branches: Mapped[list[str]] = mapped_column(JSONB)
    auto: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))


# An instance may only start on a PUBLISHED template version (a FK can't check
# a column value on the referenced row). Migration 0019 creates the same guard.
_PUBLISHED_ONLY_FN = "bbz_forbid_instance_on_unpublished_version"
_PUBLISHED_ONLY_FN_DDL = DDL(  # type: ignore[no-untyped-call]
    f"CREATE OR REPLACE FUNCTION {_PUBLISHED_ONLY_FN}() RETURNS trigger "
    "LANGUAGE plpgsql AS $$ DECLARE lc text; BEGIN "
    "SELECT lifecycle INTO lc FROM workflow_template_versions WHERE id = NEW.template_version_id; "
    "IF lc IS DISTINCT FROM 'published' THEN "
    "RAISE EXCEPTION 'workflow_instances: template_version_id must reference a published version'; "
    "END IF; RETURN NEW; END; $$"
)
_PUBLISHED_ONLY_TRIGGER_DDL = DDL(  # type: ignore[no-untyped-call]
    "CREATE TRIGGER workflow_instances_published_version BEFORE INSERT ON workflow_instances "
    f"FOR EACH ROW EXECUTE FUNCTION {_PUBLISHED_ONLY_FN}()"
)
event.listen(
    WorkflowInstance.__table__,
    "after_create",
    _PUBLISHED_ONLY_FN_DDL.execute_if(dialect="postgresql"),
)
event.listen(
    WorkflowInstance.__table__,
    "after_create",
    _PUBLISHED_ONLY_TRIGGER_DDL.execute_if(dialect="postgresql"),
)
