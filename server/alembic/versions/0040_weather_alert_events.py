"""weather_alert_events

Revision ID: 0040_weather_alert_events
Revises: 0039_weather_refresh_state
Create Date: 2026-09-01

Roadmap E18-08. Links a BBZ event to the DWD warning it was created from (one
row per event). ``weather_alert_id`` is SET NULL so the link + its ``source_ref``
survive a later refresh dropping the alert. Additive, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_weather_alert_events"
down_revision: str | None = "0039_weather_refresh_state"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "weather_alert_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("weather_alert_id", sa.Uuid(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("assessment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["weather_alert_id"],
            ["weather_alerts.id"],
            name=op.f("fk_weather_alert_events_weather_alert_id_weather_alerts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_weather_alert_events_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_weather_alert_events_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weather_alert_events")),
        sa.UniqueConstraint("event_id", name=op.f("uq_weather_alert_events_event_id")),
    )
    op.create_index(
        op.f("ix_weather_alert_events_weather_alert_id"),
        "weather_alert_events",
        ["weather_alert_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_weather_alert_events_weather_alert_id"), table_name="weather_alert_events"
    )
    op.drop_table("weather_alert_events")
