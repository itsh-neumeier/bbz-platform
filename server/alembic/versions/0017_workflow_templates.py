"""workflow_templates + workflow_template_versions (ADR-0005)

Revision ID: 0017_workflow_templates
Revises: 0016_audit_immutability
Create Date: 2026-08-30

Roadmap E05-03. Template head + immutable-once-published versions. A trigger
forbids changing a published version's ``definition``. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_workflow_templates"
down_revision: str | None = "0016_audit_immutability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FN = "bbz_forbid_published_definition_change"


def upgrade() -> None:
    op.create_table(
        "workflow_templates",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_workflow_templates_owner_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_templates")),
        sa.UniqueConstraint("key", name=op.f("uq_workflow_templates_key")),
    )
    op.create_table(
        "workflow_template_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("lifecycle", sa.String(length=16), server_default="draft", nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "lifecycle IN ('draft', 'validated', 'published', 'deprecated')",
            name=op.f("ck_workflow_template_versions_lifecycle"),
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["users.id"],
            name=op.f("fk_workflow_template_versions_published_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["workflow_templates.id"],
            name=op.f("fk_workflow_template_versions_template_id_workflow_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_template_versions")),
        sa.UniqueConstraint("template_id", "version_no", name="uq_wtv_template_version"),
    )
    op.create_index(
        op.f("ix_workflow_template_versions_lifecycle"),
        "workflow_template_versions",
        ["lifecycle"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_template_versions_template_id"),
        "workflow_template_versions",
        ["template_id"],
        unique=False,
    )
    op.execute(
        f"CREATE OR REPLACE FUNCTION {_FN}() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN "
        "IF OLD.lifecycle = 'published' AND NEW.definition IS DISTINCT FROM OLD.definition THEN "
        "RAISE EXCEPTION 'workflow_template_versions: a published definition is immutable'; "
        "END IF; RETURN NEW; END; $$"
    )
    op.execute(
        "CREATE TRIGGER workflow_template_versions_freeze_published BEFORE UPDATE "
        f"ON workflow_template_versions FOR EACH ROW EXECUTE FUNCTION {_FN}()"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS workflow_template_versions_freeze_published "
        "ON workflow_template_versions"
    )
    op.execute(f"DROP FUNCTION IF EXISTS {_FN}()")
    op.drop_index(
        op.f("ix_workflow_template_versions_template_id"),
        table_name="workflow_template_versions",
    )
    op.drop_index(
        op.f("ix_workflow_template_versions_lifecycle"),
        table_name="workflow_template_versions",
    )
    op.drop_table("workflow_template_versions")
    op.drop_table("workflow_templates")
