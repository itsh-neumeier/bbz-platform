"""weather_refresh_state

Revision ID: 0039_weather_refresh_state
Revises: 0038_weather_schema
Create Date: 2026-09-01

Roadmap E18-06. One row per weather data kind (warnings / radar / observations):
last poll attempt / success / error / item count. The refresh singleton writes
it; the weather health status is computed from it. Additive, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_weather_refresh_state"
down_revision: str | None = "0038_weather_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "weather_refresh_state",
        sa.Column("data_kind", sa.String(length=16), nullable=False),
        sa.Column("last_attempt_at", _TS, nullable=True),
        sa.Column("last_success_at", _TS, nullable=True),
        sa.Column("last_item_count", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("data_kind", name=op.f("pk_weather_refresh_state")),
    )


def downgrade() -> None:
    op.drop_table("weather_refresh_state")
