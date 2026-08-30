"""workflow_graph_nodes / workflow_graph_edges: derived graph index

Revision ID: 0018_workflow_graph_index
Revises: 0017_workflow_templates
Create Date: 2026-08-30

Roadmap E05-04. Flattened, queryable projection of a template version's graph
``definition``; rebuilt deterministically by
``bbz_core.infra.repositories.workflow_graph.rebuild_graph_index``. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_workflow_graph_index"
down_revision: str | None = "0017_workflow_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK = "workflow_template_versions.id"


def upgrade() -> None:
    op.create_table(
        "workflow_graph_nodes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("template_version_id", sa.Uuid(), nullable=False),
        sa.Column("node_key", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=16), nullable=False),
        sa.Column("function_kind", sa.String(length=32), nullable=True),
        sa.Column("connector_type", sa.String(length=8), nullable=True),
        sa.Column("connector_direction", sa.String(length=8), nullable=True),
        sa.Column("label", sa.String(length=300), nullable=True),
        sa.Column(
            "props",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["template_version_id"],
            [_FK],
            name=op.f("fk_workflow_graph_nodes_template_version_id_workflow_template_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_graph_nodes")),
        sa.UniqueConstraint("template_version_id", "node_key", name="uq_wgn_version_key"),
    )
    op.create_index(
        op.f("ix_workflow_graph_nodes_template_version_id"),
        "workflow_graph_nodes",
        ["template_version_id"],
        unique=False,
    )
    op.create_table(
        "workflow_graph_edges",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("template_version_id", sa.Uuid(), nullable=False),
        sa.Column("edge_key", sa.String(length=64), nullable=False),
        sa.Column("from_node_key", sa.String(length=64), nullable=False),
        sa.Column("to_node_key", sa.String(length=64), nullable=False),
        sa.Column("branch_label", sa.String(length=64), nullable=True),
        sa.Column("condition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["template_version_id"],
            [_FK],
            name=op.f("fk_workflow_graph_edges_template_version_id_workflow_template_versions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_graph_edges")),
        sa.UniqueConstraint("template_version_id", "edge_key", name="uq_wge_version_key"),
    )
    for col in ("from_node_key", "template_version_id", "to_node_key"):
        op.create_index(
            op.f(f"ix_workflow_graph_edges_{col}"),
            "workflow_graph_edges",
            [col],
            unique=False,
        )


def downgrade() -> None:
    for col in ("to_node_key", "template_version_id", "from_node_key"):
        op.drop_index(op.f(f"ix_workflow_graph_edges_{col}"), table_name="workflow_graph_edges")
    op.drop_table("workflow_graph_edges")
    op.drop_index(
        op.f("ix_workflow_graph_nodes_template_version_id"),
        table_name="workflow_graph_nodes",
    )
    op.drop_table("workflow_graph_nodes")
