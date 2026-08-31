"""technical_endpoints: Siedle door-station fields

Revision ID: 0035_door_station_fields
Revises: 0034_camera_mappings
Create Date: 2026-08-31

Roadmap E17-01. A door station is a ``technical_endpoint`` of type
``door_station`` (INTEGRATIONS_SIEDLE.md "Technical endpoint model"). This adds
its extra config: the door-open DTMF **profile reference** (an id only — the code
lives encrypted in ``door_action_profiles``, E17-02, never here), the operator
popup text and the door-open timeout. Additive / expand-only, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_door_station_fields"
down_revision: str | None = "0034_camera_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "technical_endpoints",
        sa.Column("dtmf_profile_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "technical_endpoints",
        sa.Column("popup_text", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "technical_endpoints",
        sa.Column("door_open_timeout_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("technical_endpoints", "door_open_timeout_seconds")
    op.drop_column("technical_endpoints", "popup_text")
    op.drop_column("technical_endpoints", "dtmf_profile_id")
