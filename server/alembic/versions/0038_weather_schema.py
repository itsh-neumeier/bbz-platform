"""weather_alerts, weather_observations

Revision ID: 0038_weather_schema
Revises: 0037_door_open_commands
Create Date: 2026-09-01

Roadmap E18-05. Persisted snapshots of DWD's published state (MASTER_PROMPT §14):
``weather_alerts`` — one normalized warning per (source_ref, region);
``weather_observations`` — one station measurement per (place, metric,
observed_at). The refresh singleton (E18-06) upserts on those keys. All times are
``timestamptz`` (ADR-0017). Additive / expand-only, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_weather_schema"
down_revision: str | None = "0037_door_open_commands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "weather_alerts",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=120), nullable=False),
        sa.Column("level", sa.String(length=32), nullable=False),
        sa.Column("valid_from", _TS, nullable=True),
        sa.Column("valid_to", _TS, nullable=True),
        sa.Column("headline", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_ref", sa.String(length=200), nullable=False),
        sa.Column("received_at", _TS, nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weather_alerts")),
        sa.UniqueConstraint("source_ref", "region", name="uq_weather_alerts_source_region"),
    )
    op.create_index(op.f("ix_weather_alerts_region"), "weather_alerts", ["region"], unique=False)
    op.create_index(
        op.f("ix_weather_alerts_source_ref"), "weather_alerts", ["source_ref"], unique=False
    )

    op.create_table(
        "weather_observations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("place", sa.String(length=120), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("observed_at", _TS, nullable=False),
        sa.Column("station_ref", sa.String(length=64), nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weather_observations")),
        sa.UniqueConstraint(
            "place", "metric", "observed_at", name="uq_weather_observations_place_metric_time"
        ),
    )
    op.create_index(
        op.f("ix_weather_observations_place"), "weather_observations", ["place"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_weather_observations_place"), table_name="weather_observations")
    op.drop_table("weather_observations")
    op.drop_index(op.f("ix_weather_alerts_source_ref"), table_name="weather_alerts")
    op.drop_index(op.f("ix_weather_alerts_region"), table_name="weather_alerts")
    op.drop_table("weather_alerts")
