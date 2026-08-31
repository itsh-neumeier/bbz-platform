"""trigger_rules, trigger_rule_versions, trigger_executions

Revision ID: 0031_trigger_rules
Revises: 0030_technical_endpoints
Create Date: 2026-08-31

Roadmap E15-02 (.ai/TECHNICAL_TRIGGERS.md, ADR-0010). Versioned condition→action
rules. A *published* version is frozen by a BEFORE UPDATE trigger. The
``trigger_executions`` UNIQUE(provider_event_id, rule_version_id, action_index)
is the engine's exactly-once key (E15-09). Reversible, expand-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_trigger_rules"
down_revision: str | None = "0030_technical_endpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIFECYCLE = ("draft", "validated", "published", "retired")
_EXEC_STATUS = ("pending", "succeeded", "failed", "skipped")
_FN = "bbz_forbid_published_trigger_change"


def _q(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _ts(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if not nullable else None,
        nullable=nullable,
    )


def upgrade() -> None:
    op.create_table(
        "trigger_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("endpoint_id", sa.Uuid(), nullable=True),
        sa.Column("lifecycle", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("100"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.CheckConstraint(f"lifecycle IN ({_q(_LIFECYCLE)})", name="lifecycle"),
        sa.ForeignKeyConstraint(
            ["endpoint_id"],
            ["technical_endpoints.id"],
            name=op.f("fk_trigger_rules_endpoint_id_technical_endpoints"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trigger_rules")),
    )
    op.create_index(op.f("ix_trigger_rules_endpoint_id"), "trigger_rules", ["endpoint_id"])
    op.create_index(op.f("ix_trigger_rules_lifecycle"), "trigger_rules", ["lifecycle"])

    op.create_table(
        "trigger_rule_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column(
            "conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "actions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("changelog", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(f"lifecycle IN ({_q(_LIFECYCLE)})", name="lifecycle"),
        sa.ForeignKeyConstraint(
            ["rule_id"],
            ["trigger_rules.id"],
            name=op.f("fk_trigger_rule_versions_rule_id_trigger_rules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["users.id"],
            name=op.f("fk_trigger_rule_versions_published_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trigger_rule_versions")),
        sa.UniqueConstraint("rule_id", "version_no", name="uq_trigger_rule_versions_rule_version"),
    )
    op.create_index(op.f("ix_trigger_rule_versions_rule_id"), "trigger_rule_versions", ["rule_id"])
    op.create_index(
        op.f("ix_trigger_rule_versions_lifecycle"), "trigger_rule_versions", ["lifecycle"]
    )

    op.create_table(
        "trigger_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_event_id", sa.Uuid(), nullable=False),
        sa.Column("rule_version_id", sa.Uuid(), nullable=False),
        sa.Column("action_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        _ts("created_at"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"status IN ({_q(_EXEC_STATUS)})", name="status"),
        sa.ForeignKeyConstraint(
            ["provider_event_id"],
            ["provider_event_inbox.id"],
            name=op.f("fk_trigger_executions_provider_event_id_provider_event_inbox"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rule_version_id"],
            ["trigger_rule_versions.id"],
            name=op.f("fk_trigger_executions_rule_version_id_trigger_rule_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trigger_executions")),
        sa.UniqueConstraint(
            "provider_event_id",
            "rule_version_id",
            "action_index",
            name="uq_trigger_executions_event_version_action",
        ),
    )
    op.create_index(
        op.f("ix_trigger_executions_provider_event_id"),
        "trigger_executions",
        ["provider_event_id"],
    )
    op.create_index(
        op.f("ix_trigger_executions_rule_version_id"),
        "trigger_executions",
        ["rule_version_id"],
    )

    op.execute(
        f"CREATE OR REPLACE FUNCTION {_FN}() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN "
        "IF OLD.lifecycle = 'published' AND ("
        "NEW.conditions IS DISTINCT FROM OLD.conditions OR "
        "NEW.actions IS DISTINCT FROM OLD.actions) THEN "
        "RAISE EXCEPTION 'trigger_rule_versions: a published version is immutable'; "
        "END IF; RETURN NEW; END; $$"
    )
    op.execute(
        "CREATE TRIGGER trigger_rule_versions_freeze_published BEFORE UPDATE "
        f"ON trigger_rule_versions FOR EACH ROW EXECUTE FUNCTION {_FN}()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trigger_rule_versions_freeze_published ON trigger_rule_versions"
    )
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}()")
    for ix in ("provider_event_id", "rule_version_id"):
        op.drop_index(op.f(f"ix_trigger_executions_{ix}"), table_name="trigger_executions")
    op.drop_table("trigger_executions")
    for ix in ("rule_id", "lifecycle"):
        op.drop_index(op.f(f"ix_trigger_rule_versions_{ix}"), table_name="trigger_rule_versions")
    op.drop_table("trigger_rule_versions")
    for ix in ("endpoint_id", "lifecycle"):
        op.drop_index(op.f(f"ix_trigger_rules_{ix}"), table_name="trigger_rules")
    op.drop_table("trigger_rules")
