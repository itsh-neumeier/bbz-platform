"""Idempotent RBAC seed — the permission catalog and the built-in roles.

Applied by migration ``0008_seed_rbac`` and re-usable at runtime (a bootstrap
command, tests). Safe to run repeatedly.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization.builtin_roles import BUILTIN_ROLES
from bbz_core.authorization.keys import CATALOG

_INS_PERM = text("INSERT INTO permissions (key, area) VALUES (:k, :a) ON CONFLICT (key) DO NOTHING")
_INS_ROLE = text(
    "INSERT INTO roles (key, name, builtin) VALUES (:k, :n, true) "
    "ON CONFLICT (key) DO UPDATE SET builtin = true"
)
_INS_RP = text(
    "INSERT INTO role_permissions (role_id, permission_id, scope) "
    "SELECT :rid, p.id, 'global' FROM permissions p WHERE p.key = :pk "
    "ON CONFLICT (role_id, permission_id, scope) DO NOTHING"
)


async def seed_rbac(session: AsyncSession) -> None:
    for area, keys in CATALOG.items():
        for key in keys:
            await session.execute(_INS_PERM, {"k": key, "a": area})
    for role_key, (name, grant_keys) in BUILTIN_ROLES.items():
        await session.execute(_INS_ROLE, {"k": role_key, "n": name})
        role_id = (
            await session.execute(text("SELECT id FROM roles WHERE key = :k"), {"k": role_key})
        ).scalar_one()
        for pkey in sorted(grant_keys):
            await session.execute(_INS_RP, {"rid": role_id, "pk": pkey})
    await session.commit()
