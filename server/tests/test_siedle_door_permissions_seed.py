"""Door / technical-endpoint permission catalog + least-privilege defaults (E17-07).

The six keys are seeded by the generic 0008 migration (it iterates ``CATALOG`` /
``BUILTIN_ROLES``). This test locks the *policy*: opening a door is an operator
action, but configuring the DTMF profile / managing endpoints stays senior, and a
read-only role can at most look.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization import BUILTIN_ROLES, CATALOG

_DOOR_KEYS = {
    "door.view",
    "door.answer",
    "door.open",
    "door.configure",
    "technical_endpoints.view",
    "technical_endpoints.manage",
}
#: writing config — the DTMF profile ref, endpoint CRUD — is senior only
_SENIOR_ONLY = {"door.configure", "technical_endpoints.manage"}
_SENIOR = {"administrator", "sichtleiter"}


def _grants(role_key: str) -> frozenset[str]:
    return BUILTIN_ROLES[role_key][1]


def test_all_six_door_keys_are_in_the_catalog() -> None:
    assert set(CATALOG["door_technical"]) == _DOOR_KEYS


def test_operators_can_open_but_not_configure() -> None:
    disp = _grants("disponent")
    assert {"door.view", "door.answer", "door.open"} <= disp
    assert "door.configure" not in disp
    assert "technical_endpoints.manage" not in disp


def test_config_keys_are_senior_only() -> None:
    for key in _SENIOR_ONLY:
        holders = {r for r in BUILTIN_ROLES if key in _grants(r)}
        assert holders <= _SENIOR, f"{key} granted to non-senior: {holders - _SENIOR}"


def test_read_only_role_can_at_most_look() -> None:
    door = {k for k in _grants("nur_lesen") if k in _DOOR_KEYS}
    assert door <= {"door.view", "technical_endpoints.view"}


@pytest.mark.parametrize("role", sorted(BUILTIN_ROLES))
def test_no_builtin_role_grants_an_unknown_door_key(role: str) -> None:
    held = {k for k in _grants(role) if k.startswith(("door.", "technical_endpoints."))}
    assert held <= _DOOR_KEYS


async def test_the_seed_actually_wrote_the_door_grants(db: object) -> None:
    from bbz_core.authorization.seed import seed_rbac

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await seed_rbac(s)

    present = {
        r[0]
        for r in (
            await s.execute(text("SELECT key FROM permissions WHERE area = 'door_technical'"))
        ).all()
    }
    assert present == _DOOR_KEYS

    rows = (
        await s.execute(
            text(
                "SELECT r.key, p.key FROM role_permissions rp "
                "JOIN roles r ON r.id = rp.role_id "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE p.area = 'door_technical'"
            )
        )
    ).all()
    by_role: dict[str, set[str]] = {}
    for role, perm in rows:
        by_role.setdefault(role, set()).add(perm)

    assert by_role.get("administrator", set()) == _DOOR_KEYS
    assert {"door.view", "door.answer", "door.open"} <= by_role.get("disponent", set())
    assert "door.configure" not in by_role.get("disponent", set())
    assert by_role.get("nur_lesen", set()) <= {"door.view", "technical_endpoints.view"}
