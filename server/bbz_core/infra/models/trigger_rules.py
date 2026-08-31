"""Trigger rules — versioned condition→action rules for inbound signals (E15-02).

``.ai/TECHNICAL_TRIGGERS.md`` / ADR-0010: rules are **admin-configurable and
versioned**; a *published* version is immutable — any change makes a new
version. Conditions are DSL JSON over allowlisted normalized fields (E15-05),
actions are typed (E15-06..08) — never arbitrary code.

``trigger_executions`` is the exactly-once ledger: one row per
``(provider_event_id, rule_version_id, action_index)`` — the UNIQUE key the
engine (E15-09) uses so a replayed provider event never fires an action twice.
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

from bbz_core.infra.models.base import Base, TimestampMixin, uuid_pk


class TriggerLifecycle(enum.StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    RETIRED = "retired"


class TriggerExecutionStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


_LIFECYCLE = ", ".join(f"'{v.value}'" for v in TriggerLifecycle)
_EXEC_STATUS = ", ".join(f"'{v.value}'" for v in TriggerExecutionStatus)


class TriggerRule(Base, TimestampMixin):
    __tablename__ = "trigger_rules"
    __table_args__ = (CheckConstraint(f"lifecycle IN ({_LIFECYCLE})", name="lifecycle"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    #: optional binding to a specific technical endpoint; NULL = a global rule
    #: matched purely on its conditions
    endpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("technical_endpoints.id", ondelete="SET NULL"), index=True
    )
    #: the rule's current state, mirrored from its active version (E15-10)
    lifecycle: Mapped[str] = mapped_column(
        String(16), server_default=TriggerLifecycle.DRAFT.value, index=True
    )
    #: lower runs first when several rules match (E15-05 determinism)
    priority: Mapped[int] = mapped_column(Integer, server_default=text("100"))


class TriggerRuleVersion(Base):
    """One immutable-once-published snapshot of a rule's conditions + actions."""

    __tablename__ = "trigger_rule_versions"
    __table_args__ = (
        UniqueConstraint("rule_id", "version_no", name="uq_trigger_rule_versions_rule_version"),
        CheckConstraint(f"lifecycle IN ({_LIFECYCLE})", name="lifecycle"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trigger_rules.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    lifecycle: Mapped[str] = mapped_column(
        String(16), server_default=TriggerLifecycle.DRAFT.value, index=True
    )
    #: DSL condition tree over allowlisted normalized fields (E15-05)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    #: ordered list of typed actions (E15-06..08)
    actions: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    changelog: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    published_at: Mapped[_dt.datetime | None] = mapped_column()
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class TriggerExecution(Base):
    """Exactly-once ledger: one row per (provider event, rule version, action)."""

    __tablename__ = "trigger_executions"
    __table_args__ = (
        UniqueConstraint(
            "provider_event_id",
            "rule_version_id",
            "action_index",
            name="uq_trigger_executions_event_version_action",
        ),
        CheckConstraint(f"status IN ({_EXEC_STATUS})", name="status"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    provider_event_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_event_inbox.id", ondelete="CASCADE"), index=True
    )
    rule_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trigger_rule_versions.id", ondelete="CASCADE"), index=True
    )
    action_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(16), server_default=TriggerExecutionStatus.PENDING.value
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[_dt.datetime] = mapped_column(server_default=text("now()"))
    completed_at: Mapped[_dt.datetime | None] = mapped_column()


# ADR-0010: a published rule version is frozen — conditions and actions cannot
# change. The 0031 migration installs the same guard for provisioned databases.
_FROZEN_FN = "bbz_forbid_published_trigger_change"
_FROZEN_FN_DDL = DDL(  # type: ignore[no-untyped-call]
    f"CREATE OR REPLACE FUNCTION {_FROZEN_FN}() RETURNS trigger LANGUAGE plpgsql AS $$ "
    "BEGIN "
    "IF OLD.lifecycle = 'published' AND ("
    "NEW.conditions IS DISTINCT FROM OLD.conditions OR "
    "NEW.actions IS DISTINCT FROM OLD.actions) THEN "
    "RAISE EXCEPTION 'trigger_rule_versions: a published version is immutable'; "
    "END IF; RETURN NEW; END; $$"
)
_FROZEN_TRIGGER_DDL = DDL(  # type: ignore[no-untyped-call]
    "CREATE TRIGGER trigger_rule_versions_freeze_published BEFORE UPDATE "
    f"ON trigger_rule_versions FOR EACH ROW EXECUTE FUNCTION {_FROZEN_FN}()"
)
event.listen(
    TriggerRuleVersion.__table__,
    "after_create",
    _FROZEN_FN_DDL.execute_if(dialect="postgresql"),
)
event.listen(
    TriggerRuleVersion.__table__,
    "after_create",
    _FROZEN_TRIGGER_DDL.execute_if(dialect="postgresql"),
)
