"""Permission catalog + effective-permission aggregation + authorize()."""

from __future__ import annotations

import uuid

import pytest

from bbz_core.authorization import (
    CATALOG,
    PERMISSION_KEYS,
    EffectivePermissions,
    Grant,
    PermissionKeyError,
    PermissionService,
    Scope,
)
from bbz_core.authorization.keys import assert_known


def test_catalog_is_flat_unique_and_covers_known_areas() -> None:
    flat = [k for keys in CATALOG.values() for k in keys]
    assert len(flat) == len(set(flat)) == len(PERMISSION_KEYS)
    for expected in ("events.takeover", "door.open", "system.audit.view", "agents.manage"):
        assert expected in PERMISSION_KEYS


def test_assert_known_rejects_unknown_key() -> None:
    assert_known("events.view")
    with pytest.raises(PermissionKeyError):
        assert_known("events.definitely_not_real")


def test_effective_permissions_aggregate_additively() -> None:
    eff = EffectivePermissions(
        [
            Grant("events.view", Scope.GLOBAL.value),
            Grant("events.takeover", Scope.BBZ.value),
            Grant("events.takeover", Scope.GLOBAL.value),
        ]
    )
    assert eff.has("events.view")
    assert eff.scopes_for("events.takeover") == frozenset({"bbz", "global"})
    assert not eff.has("events.archive")
    assert eff.keys() == frozenset({"events.view", "events.takeover"})


class FakeGrantStore:
    def __init__(self, grants: list[Grant]) -> None:
        self._grants = grants
        self.calls = 0

    async def grants_for_user(self, user_id: uuid.UUID) -> list[Grant]:
        self.calls += 1
        return list(self._grants)


async def test_authorize_and_request_cache() -> None:
    store = FakeGrantStore([Grant("calls.answer", "workplace")])
    svc = PermissionService(store)
    uid = uuid.uuid4()
    assert await svc.authorize(uid, "calls.answer") is True
    assert await svc.authorize(uid, "calls.hangup") is False
    assert await svc.effective(uid) is await svc.effective(uid)
    assert store.calls == 1  # memoised for the life of the (request-scoped) service


async def test_authorize_unknown_key_raises_never_allows() -> None:
    svc = PermissionService(FakeGrantStore([Grant("nonsense.key", "global")]))
    with pytest.raises(PermissionKeyError):
        await svc.authorize(uuid.uuid4(), "nonsense.key")


async def test_grant_order_is_irrelevant() -> None:
    a = [Grant("events.view", "global"), Grant("events.edit", "bbz")]
    assert EffectivePermissions(a).keys() == EffectivePermissions(list(reversed(a))).keys()


async def test_grant_store_unions_direct_and_group_roles(db: object) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from bbz_core.infra.models.identity import User
    from bbz_core.infra.models.rbac import (
        Group,
        GroupRole,
        Permission,
        Role,
        RolePermission,
        UserGroup,
        UserRole,
    )
    from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore

    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)

    user = User(display_name="Op")
    p_view = Permission(key="events.view", area="events")
    p_take = Permission(key="events.takeover", area="events")
    r_direct = Role(key="disponent", name="Disponent")
    r_group = Role(key="sichtleiter", name="Sichtleiter")
    grp = Group(key="schicht-a", name="Schicht A")
    s.add_all([user, p_view, p_take, r_direct, r_group, grp])
    await s.flush()
    s.add_all(
        [
            RolePermission(role_id=r_direct.id, permission_id=p_view.id, scope="global"),
            RolePermission(role_id=r_group.id, permission_id=p_take.id, scope="bbz"),
            UserRole(user_id=user.id, role_id=r_direct.id),
            GroupRole(group_id=grp.id, role_id=r_group.id),
            UserGroup(user_id=user.id, group_id=grp.id),
        ]
    )
    await s.commit()

    grants = await SqlAlchemyGrantStore(s).grants_for_user(user.id)
    eff = EffectivePermissions(grants)
    assert eff.has("events.view")
    assert eff.scopes_for("events.takeover") == frozenset({"bbz"})
