"""seed_rbac: permission catalog + five built-in roles

Revision ID: 0008_seed_rbac
Revises: 0007_local_totp
Create Date: 2026-08-29

Roadmap E02-14 (#40). Data migration — idempotent (re-runnable). Downgrade
removes only the seeded rows.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from bbz_core.authorization.builtin_roles import BUILTIN_ROLES
from bbz_core.authorization.keys import CATALOG, PERMISSION_KEYS

revision: str = "0008_seed_rbac"
down_revision: str | None = "0007_local_totp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    for area, keys in CATALOG.items():
        for key in keys:
            conn.execute(
                sa.text(
                    "INSERT INTO permissions (key, area) VALUES (:k, :a) "
                    "ON CONFLICT (key) DO NOTHING"
                ),
                {"k": key, "a": area},
            )

    for role_key, (name, grant_keys) in BUILTIN_ROLES.items():
        conn.execute(
            sa.text(
                "INSERT INTO roles (key, name, builtin) VALUES (:k, :n, true) "
                "ON CONFLICT (key) DO UPDATE SET builtin = true"
            ),
            {"k": role_key, "n": name},
        )
        role_id = conn.execute(
            sa.text("SELECT id FROM roles WHERE key = :k"), {"k": role_key}
        ).scalar_one()
        for pkey in sorted(grant_keys):
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id, scope) "
                    "SELECT :rid, p.id, 'global' FROM permissions p WHERE p.key = :pk "
                    "ON CONFLICT (role_id, permission_id, scope) DO NOTHING"
                ),
                {"rid": role_id, "pk": pkey},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM roles WHERE key = ANY(:keys)"),
        {"keys": list(BUILTIN_ROLES)},  # cascades to role_permissions / user_roles
    )
    conn.execute(
        sa.text("DELETE FROM permissions WHERE key = ANY(:keys)"),
        {"keys": sorted(PERMISSION_KEYS)},
    )
