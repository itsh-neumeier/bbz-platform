"""app_settings

Revision ID: 0055_app_settings
Revises: 0054_uuid_pk_defaults
Create Date: 2026-09-03

Roadmap #720 / ADR-0031. A DB overlay over the env-based ``Settings``: one row
per overridden key, ``value`` as JSONB. Absence of a row means "not overridden"
— the value then resolves from the environment / code default exactly as before.
Written only through the admin settings API (``system.settings.manage``), every
change audited ``SETTING_CHANGED``.

Additive, standalone table. Reversible.

expand-contract: safe
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0055_app_settings"
down_revision: str | None = "0054_uuid_pk_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_app_settings_updated_by_users"),
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
