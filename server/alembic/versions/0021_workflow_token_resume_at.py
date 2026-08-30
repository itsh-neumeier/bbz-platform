"""workflow token resume_at (timer tasks)

Revision ID: 0021_workflow_token_resume_at
Revises: 0020_workflow_token_inbound_edge
Create Date: 2026-08-30

Roadmap E05-10. ``workflow_tokens.resume_at`` is when a parked ``timer`` task
is due to resume; persisting it means the timer still fires after a restart.
Reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_workflow_token_resume_at"
down_revision: str | None = "0020_workflow_token_inbound_edge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workflow_tokens",
        sa.Column("resume_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_workflow_tokens_resume_at"), "workflow_tokens", ["resume_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workflow_tokens_resume_at"), table_name="workflow_tokens")
    op.drop_column("workflow_tokens", "resume_at")
