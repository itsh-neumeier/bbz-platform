"""workflow token inbound edge key

Revision ID: 0020_workflow_token_inbound_edge
Revises: 0019_workflow_runtime
Create Date: 2026-08-30

Roadmap E05-08. ``workflow_tokens.inbound_edge_key`` records which edge a token
arrived on so an AND join can tell its incoming branches apart. Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_workflow_token_inbound_edge"
down_revision: str | None = "0019_workflow_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_tokens",
        sa.Column("inbound_edge_key", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflow_tokens", "inbound_edge_key")
