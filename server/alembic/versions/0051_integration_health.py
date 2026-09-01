"""integration_health

Revision ID: 0051_integration_health
Revises: 0050_account_linking
Create Date: 2026-09-02

Roadmap E22-05 / MASTER_PROMPT §14, §8.14. One row per integration (keyed by the
manifest id) with a normalised health state, the check / last-ok / last-error
timestamps, a consecutive-error counter and the last observed activity. Written
by the ``integration-health`` singleton and refreshed on
``GET /api/v1/integrations/health``. All times ``timestamptz`` (ADR-0017).
Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_integration_health"
down_revision: str | None = "0050_account_linking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "integration_health",
        sa.Column("integration_id", sa.String(length=64), nullable=False),
        sa.Column("domain", sa.String(length=32), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="down"),
        sa.Column("summary", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("checked_at", _TS, nullable=True),
        sa.Column("last_ok_at", _TS, nullable=True),
        sa.Column("last_error_at", _TS, nullable=True),
        sa.Column("consecutive_errors", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_activity_at", _TS, nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "state IN ('ok', 'degraded', 'down', 'disabled')", name="ck_integration_health_state"
        ),
        sa.PrimaryKeyConstraint("integration_id", name=op.f("pk_integration_health")),
    )


def downgrade() -> None:
    op.drop_table("integration_health")
