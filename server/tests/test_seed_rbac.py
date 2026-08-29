"""The 0008 seed migration: catalog + built-in roles, idempotent, reversible."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization import BUILTIN_ROLES, PERMISSION_KEYS


@pytest.fixture
async def seeded(db: object) -> AsyncSession:
    """Apply the 0008 seed on top of the schema the ``db`` fixture created."""
    from bbz_core.authorization.seed import seed_rbac

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await seed_rbac(s)
    return s


async def test_all_catalog_permissions_present(seeded: AsyncSession) -> None:
    keys = {r[0] for r in (await seeded.execute(text("SELECT key FROM permissions"))).all()}
    assert keys >= PERMISSION_KEYS


async def test_five_builtin_roles(seeded: AsyncSession) -> None:
    rows = (await seeded.execute(text("SELECT key, builtin FROM roles ORDER BY key"))).all()
    assert {r[0] for r in rows} == set(BUILTIN_ROLES)
    assert all(r[1] for r in rows)


async def test_administrator_can_manage_and_read_only_only_views(seeded: AsyncSession) -> None:
    async def grants(role_key: str) -> set[str]:
        return {
            r[0]
            for r in (
                await seeded.execute(
                    text(
                        "SELECT p.key FROM role_permissions rp "
                        "JOIN permissions p ON p.id = rp.permission_id "
                        "JOIN roles r ON r.id = rp.role_id WHERE r.key = :k"
                    ),
                    {"k": role_key},
                )
            ).all()
        }

    admin = await grants("administrator")
    assert admin == PERMISSION_KEYS

    read_only = await grants("nur_lesen")
    assert read_only and all(k.rsplit(".", 1)[-1] == "view" for k in read_only)


async def test_seed_is_idempotent(seeded: AsyncSession) -> None:
    from bbz_core.authorization.seed import seed_rbac

    before = (await seeded.execute(text("SELECT count(*) FROM role_permissions"))).scalar_one()
    await seed_rbac(seeded)
    after = (await seeded.execute(text("SELECT count(*) FROM role_permissions"))).scalar_one()
    assert before == after
