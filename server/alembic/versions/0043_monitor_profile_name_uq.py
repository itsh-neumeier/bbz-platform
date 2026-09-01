"""monitor_profiles: unique name per scope owner

Revision ID: 0043_monitor_profile_name_uq
Revises: 0042_monitor_catalog_seed
Create Date: 2026-09-01

Roadmap E19-05. A layout profile name is unique within its scope: per
``owner_user_id`` for ``user`` profiles, per ``workplace_id`` for ``workplace``
profiles. Two partial unique indexes. Additive / expand-only, reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0043_monitor_profile_name_uq"
down_revision: str | None = "0042_monitor_catalog_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_monitor_profiles_user_name",
        "monitor_profiles",
        ["owner_user_id", "name"],
        unique=True,
        postgresql_where="scope = 'user'",
    )
    op.create_index(
        "uq_monitor_profiles_workplace_name",
        "monitor_profiles",
        ["workplace_id", "name"],
        unique=True,
        postgresql_where="scope = 'workplace'",
    )


def downgrade() -> None:
    op.drop_index("uq_monitor_profiles_workplace_name", table_name="monitor_profiles")
    op.drop_index("uq_monitor_profiles_user_name", table_name="monitor_profiles")
