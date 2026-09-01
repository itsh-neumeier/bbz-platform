"""Monitor permission catalog + least-privilege role defaults (E19-09).

The four ``monitor.*`` keys are seeded by the generic 0008 migration (it iterates
``CATALOG`` / ``BUILTIN_ROLES`` at runtime). This test locks the *policy*: routing
is a Disponent action, reset-standard and profile management are senior, and a
read-only role can at most look."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization import BUILTIN_ROLES, CATALOG

_MONITOR_KEYS = {
    "monitor.view",
    "monitor.route",
    "monitor.reset_standard",
    "monitor.manage_profiles",
}
_SENIOR = {"administrator", "sichtleiter"}
#: switching a whole layout back / owning saved profiles — senior only
_SENIOR_ONLY = {"monitor.reset_standard", "monitor.manage_profiles"}


def _grants(role_key: str) -> frozenset[str]:
    return BUILTIN_ROLES[role_key][1]


def test_all_four_monitor_keys_are_in_the_catalog() -> None:
    assert set(CATALOG["monitor"]) == _MONITOR_KEYS


def test_senior_only_monitor_actions() -> None:
    for key in _SENIOR_ONLY:
        holders = {r for r in BUILTIN_ROLES if key in _grants(r)}
        assert holders <= _SENIOR, f"{key} granted to non-senior roles: {holders - _SENIOR}"


def test_disponent_can_route_but_not_reset_or_manage_profiles() -> None:
    d = {k for k in _grants("disponent") if k.startswith("monitor.")}
    assert d == {"monitor.view", "monitor.route"}


def test_read_only_role_can_at_most_look() -> None:
    read_only = {k for k in _grants("nur_lesen") if k.startswith("monitor.")}
    assert read_only <= {"monitor.view"}


def test_senior_roles_have_the_full_set() -> None:
    for role in _SENIOR:
        assert {k for k in _grants(role) if k.startswith("monitor.")} == _MONITOR_KEYS


@pytest.mark.parametrize("role", sorted(BUILTIN_ROLES))
def test_no_builtin_role_grants_an_unknown_monitor_key(role: str) -> None:
    assert {k for k in _grants(role) if k.startswith("monitor.")} <= _MONITOR_KEYS


async def test_the_seed_actually_wrote_the_monitor_grants(db: object) -> None:
    from bbz_core.authorization.seed import seed_rbac

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await seed_rbac(s)

    present = {
        r[0]
        for r in (await s.execute(text("SELECT key FROM permissions WHERE area = 'monitor'"))).all()
    }
    assert present == _MONITOR_KEYS

    rows = (
        await s.execute(
            text(
                "SELECT r.key, p.key FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE p.area = 'monitor'"
            )
        )
    ).all()
    by_role: dict[str, set[str]] = {}
    for role, perm in rows:
        by_role.setdefault(role, set()).add(perm)

    assert by_role.get("administrator", set()) == _MONITOR_KEYS
    assert by_role.get("sichtleiter", set()) == _MONITOR_KEYS
    assert by_role.get("disponent", set()) == {"monitor.view", "monitor.route"}
    assert by_role.get("nachbearbeitung", set()) == set()
    assert by_role.get("nur_lesen", set()) <= {"monitor.view"}
