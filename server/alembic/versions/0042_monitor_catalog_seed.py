"""seed_monitor_catalog: the fixed input/output catalog + the standard layout

Revision ID: 0042_monitor_catalog_seed
Revises: 0041_monitor_schema
Create Date: 2026-09-01

Roadmap E19-02. Data migration — idempotent (re-runnable). Seeds the seven
logical inputs and seven outputs (MASTER_PROMPT §9) from
``bbz_core.domain.monitor.catalog`` and the documented standard layout into
``monitor_routes``. Downgrade removes only the seeded rows.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from bbz_core.domain.monitor.catalog import INPUTS, OUTPUTS, STANDARD_LAYOUT

revision: str = "0042_monitor_catalog_seed"
down_revision: str | None = "0041_monitor_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    for i in INPUTS:
        conn.execute(
            sa.text(
                "INSERT INTO monitor_inputs (key, label, sort_order) "
                "VALUES (:k, :l, :s) ON CONFLICT (key) DO NOTHING"
            ),
            {"k": i.key, "l": i.label, "s": i.sort_order},
        )

    for o in OUTPUTS:
        conn.execute(
            sa.text(
                "INSERT INTO monitor_outputs "
                "(key, label, grid_row, grid_col, is_large_display, sort_order) "
                "VALUES (:k, :l, :r, :c, :large, :s) ON CONFLICT (key) DO NOTHING"
            ),
            {
                "k": o.key,
                "l": o.label,
                "r": o.grid_row,
                "c": o.grid_col,
                "large": o.is_large_display,
                "s": o.sort_order,
            },
        )

    for output_key, input_key in STANDARD_LAYOUT.items():
        conn.execute(
            sa.text(
                "INSERT INTO monitor_routes (output_id, input_id, set_at) "
                "SELECT o.id, i.id, now() FROM monitor_outputs o, monitor_inputs i "
                "WHERE o.key = :ok AND i.key = :ik "
                "ON CONFLICT (output_id) DO NOTHING"
            ),
            {"ok": output_key, "ik": input_key},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM monitor_routes WHERE output_id IN "
            "(SELECT id FROM monitor_outputs WHERE key = ANY(:keys))"
        ),
        {"keys": [o.key for o in OUTPUTS]},
    )
    conn.execute(
        sa.text("DELETE FROM monitor_outputs WHERE key = ANY(:keys)"),
        {"keys": [o.key for o in OUTPUTS]},
    )
    conn.execute(
        sa.text("DELETE FROM monitor_inputs WHERE key = ANY(:keys)"),
        {"keys": [i.key for i in INPUTS]},
    )
