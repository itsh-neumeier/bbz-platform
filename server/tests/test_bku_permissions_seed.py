"""BKU permission catalog + least-privilege role defaults (E10-14).

The eight ``bku.*`` keys are seeded by the generic 0008 migration (it iterates
``CATALOG`` / ``BUILTIN_ROLES``). This test locks the *policy*: the high-impact
actions stay with the senior roles, and a read-only role can at most look.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization import BUILTIN_ROLES, CATALOG

_BKU_KEYS = {
    "bku.status.view",
    "bku.apps.launch",
    "bku.apps.close",
    "bku.session.logout",
    "bku.device.restart",
    "bku.catalog.view",
    "bku.catalog.manage",
    "bku.agent.manage",
}
#: actions that can end a user's session or reboot a workstation — senior only
_HIGH_IMPACT = {"bku.session.logout", "bku.device.restart"}
_SENIOR = {"administrator", "sichtleiter"}


def _grants(role_key: str) -> frozenset[str]:
    return BUILTIN_ROLES[role_key][1]


def test_all_eight_bku_keys_are_in_the_catalog() -> None:
    assert set(CATALOG["bku"]) == _BKU_KEYS


def test_high_impact_bku_actions_are_senior_only() -> None:
    for key in _HIGH_IMPACT:
        holders = {r for r in BUILTIN_ROLES if key in _grants(r)}
        assert holders <= _SENIOR, f"{key} is granted to non-senior roles: {holders - _SENIOR}"


def test_read_only_role_can_at_most_look() -> None:
    read_only = {k for k in _grants("nur_lesen") if k.startswith("bku.")}
    assert read_only <= {"bku.status.view", "bku.catalog.view"}


def test_catalog_manage_and_agent_manage_are_senior_only() -> None:
    for key in ("bku.catalog.manage", "bku.agent.manage"):
        holders = {r for r in BUILTIN_ROLES if key in _grants(r)}
        assert holders <= _SENIOR


async def test_the_seed_actually_wrote_the_bku_grants(db: object) -> None:
    from bbz_core.authorization.seed import seed_rbac

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await seed_rbac(s)

    present = {
        r[0]
        for r in (await s.execute(text("SELECT key FROM permissions WHERE area = 'bku'"))).all()
    }
    assert present == _BKU_KEYS

    rows = (
        await s.execute(
            text(
                "SELECT r.key, p.key FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE p.area = 'bku'"
            )
        )
    ).all()
    by_role: dict[str, set[str]] = {}
    for role, perm in rows:
        by_role.setdefault(role, set()).add(perm)

    assert by_role.get("administrator", set()) == _BKU_KEYS
    assert by_role.get("sichtleiter", set()) == _BKU_KEYS
    for key in _HIGH_IMPACT:
        assert key not in by_role.get("disponent", set())
    assert by_role.get("nur_lesen", set()) <= {"bku.status.view", "bku.catalog.view"}


@pytest.mark.parametrize("role", sorted(BUILTIN_ROLES))
def test_no_builtin_role_grants_an_unknown_bku_key(role: str) -> None:
    assert {k for k in _grants(role) if k.startswith("bku.")} <= _BKU_KEYS
