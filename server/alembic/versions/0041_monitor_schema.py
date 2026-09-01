"""monitor_inputs, monitor_outputs, monitor_routes, monitor_profiles

Revision ID: 0041_monitor_schema
Revises: 0040_weather_alert_events
Create Date: 2026-09-01

Roadmap E19-01. Monitor / KVM routing (MASTER_PROMPT §9): logical **inputs**
(BBZ-OS, BKU1-4, Cayuga 1-2), **outputs** (six workplace monitors in a 3x2 grid +
the large display), the **current route** per output (exactly one row per
output), and named **layout profiles**. Schema only — the fixed input/output
catalog and the standard layout are the E19-02 seed. All times ``timestamptz``
(ADR-0017). Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_monitor_schema"
down_revision: str | None = "0040_weather_alert_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)
_NOW = sa.text("now()")
_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "monitor_inputs",
        sa.Column("id", sa.Uuid(), server_default=_UUID_DEFAULT, nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitor_inputs")),
        sa.UniqueConstraint("key", name=op.f("uq_monitor_inputs_key")),
    )

    op.create_table(
        "monitor_outputs",
        sa.Column("id", sa.Uuid(), server_default=_UUID_DEFAULT, nullable=False),
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("grid_row", sa.SmallInteger(), nullable=True),
        sa.Column("grid_col", sa.SmallInteger(), nullable=True),
        sa.Column(
            "is_large_display", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "(is_large_display AND grid_row IS NULL AND grid_col IS NULL) OR "
            "(NOT is_large_display AND grid_row BETWEEN 0 AND 1 AND grid_col BETWEEN 0 AND 2)",
            name="monitor_outputs_grid",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitor_outputs")),
        sa.UniqueConstraint("key", name=op.f("uq_monitor_outputs_key")),
        sa.UniqueConstraint("grid_row", "grid_col", name="uq_monitor_outputs_grid_row_col"),
    )

    op.create_table(
        "monitor_profiles",
        sa.Column("id", sa.Uuid(), server_default=_UUID_DEFAULT, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("workplace_id", sa.Uuid(), nullable=True),
        sa.Column("layout", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.CheckConstraint("scope IN ('user', 'workplace')", name="monitor_profiles_scope"),
        sa.CheckConstraint(
            "(scope = 'user' AND owner_user_id IS NOT NULL AND workplace_id IS NULL) OR "
            "(scope = 'workplace' AND workplace_id IS NOT NULL AND owner_user_id IS NULL)",
            name="monitor_profiles_scope_owner",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_monitor_profiles_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_monitor_profiles")),
    )
    op.create_index(
        op.f("ix_monitor_profiles_owner_user_id"), "monitor_profiles", ["owner_user_id"]
    )
    op.create_index(op.f("ix_monitor_profiles_workplace_id"), "monitor_profiles", ["workplace_id"])

    op.create_table(
        "monitor_routes",
        sa.Column("output_id", sa.Uuid(), nullable=False),
        sa.Column("input_id", sa.Uuid(), nullable=False),
        sa.Column("set_by", sa.Uuid(), nullable=True),
        sa.Column("set_at", _TS, nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", _TS, server_default=_NOW, nullable=False),
        sa.Column("updated_at", _TS, server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["output_id"],
            ["monitor_outputs.id"],
            name=op.f("fk_monitor_routes_output_id_monitor_outputs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["input_id"],
            ["monitor_inputs.id"],
            name=op.f("fk_monitor_routes_input_id_monitor_inputs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["set_by"],
            ["users.id"],
            name=op.f("fk_monitor_routes_set_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["monitor_profiles.id"],
            name=op.f("fk_monitor_routes_profile_id_monitor_profiles"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("output_id", name=op.f("pk_monitor_routes")),
    )
    op.create_index(op.f("ix_monitor_routes_input_id"), "monitor_routes", ["input_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_monitor_routes_input_id"), table_name="monitor_routes")
    op.drop_table("monitor_routes")
    op.drop_index(op.f("ix_monitor_profiles_workplace_id"), table_name="monitor_profiles")
    op.drop_index(op.f("ix_monitor_profiles_owner_user_id"), table_name="monitor_profiles")
    op.drop_table("monitor_profiles")
    op.drop_table("monitor_outputs")
    op.drop_table("monitor_inputs")
