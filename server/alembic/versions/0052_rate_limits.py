"""rate_limit_hits

Revision ID: 0052_rate_limits
Revises: 0051_integration_health
Create Date: 2026-09-02

Roadmap E23-04 / MASTER_PROMPT §22. A cluster-wide fixed-window counter: one row
per ``(bucket, window_start)``, incremented on each hit. Both app nodes write to
the same table, so a limit is enforced across the cluster. Old windows are
pruned by the retention worker. Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_rate_limits"
down_revision: str | None = "0051_integration_health"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "rate_limit_hits",
        sa.Column("bucket", sa.String(length=160), nullable=False),
        sa.Column("window_start", _TS, nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", _TS, nullable=False),
        sa.PrimaryKeyConstraint("bucket", "window_start", name=op.f("pk_rate_limit_hits")),
    )
    op.create_index("ix_rate_limit_hits_expires_at", "rate_limit_hits", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_hits_expires_at", table_name="rate_limit_hits")
    op.drop_table("rate_limit_hits")
