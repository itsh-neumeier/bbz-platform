"""Advanced RBAC: conditions, time-bound grants, delegation (roadmap E21-07)."""

from __future__ import annotations

import datetime as _dt
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.authorization import Grant, PermissionService
from bbz_core.authorization.resolver import condition_allows
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
from bbz_core.infra.models.rbac import (
    Permission,
    PermissionDelegation,
    Role,
    RolePermission,
    UserRole,
)
from bbz_core.infra.repositories.authorization import SqlAlchemyGrantStore

_PW = "Wolke7-Bahnhof!x"


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ.update(
        {
            "BBZ_ARGON2_MEMORY_COST_KIB": "512",
            "BBZ_ARGON2_TIME_COST": "1",
            "BBZ_JWT_SECRET": "adv-rbac-test-secret-at-least-32-bytes!!",
            "BBZ_SESSION_COOKIE_SECURE": "false",
        }
    )
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    os.environ.pop("BBZ_RBAC_CONDITIONS_ENABLED", None)
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


def _enable_conditions() -> None:
    from bbz_core import settings as settings_mod

    os.environ["BBZ_RBAC_CONDITIONS_ENABLED"] = "true"
    settings_mod.get_settings.cache_clear()


# --- conditions ---------------------------------------------------------


def test_condition_allows_evaluates_the_clock() -> None:
    _enable_conditions()
    g = Grant("events.view", "global", condition={"op": "gte", "args": [{"field": "now.hour"}, 0]})
    always = _dt.datetime(2026, 1, 1, 12, 0, tzinfo=_dt.UTC)
    assert condition_allows(g, now=always) is True

    never = Grant(
        "events.view", "global", condition={"op": "lt", "args": [{"field": "now.hour"}, 0]}
    )
    assert condition_allows(never, now=always) is False


def test_condition_denies_when_the_flag_is_off() -> None:
    g = Grant("events.view", "global", condition={"op": "gte", "args": [{"field": "now.hour"}, 0]})
    assert condition_allows(g) is False  # flag defaults off


def test_a_broken_condition_is_a_deny_not_a_crash() -> None:
    _enable_conditions()
    g = Grant("events.view", "global", condition={"op": "eq", "args": []})  # bad arity
    assert condition_allows(g) is False


async def test_authorize_honours_a_condition(s: AsyncSession) -> None:
    _enable_conditions()
    uid = await _user_with_conditional_perm(
        s, "events.view", {"op": "gte", "args": [{"field": "now.hour"}, 0]}
    )
    assert await PermissionService(SqlAlchemyGrantStore(s)).authorize(uid, "events.view") is True

    uid2 = await _user_with_conditional_perm(
        s, "events.archive", {"op": "lt", "args": [{"field": "now.hour"}, 0]}
    )
    assert (
        await PermissionService(SqlAlchemyGrantStore(s)).authorize(uid2, "events.archive") is False
    )


# --- time-bound grants -----------------------------------------------


async def test_an_expired_role_grant_is_not_effective(s: AsyncSession) -> None:
    uid, rid = await _user_and_role(s, "events.view")
    now = _dt.datetime.now(_dt.UTC)
    await s.rollback()
    async with s.begin():
        await s.execute(select(UserRole).where(UserRole.user_id == uid))  # noop
        ur = await s.get(UserRole, (uid, rid))
        assert ur is not None
        ur.valid_to = now - _dt.timedelta(hours=1)

    grants = await SqlAlchemyGrantStore(s).grants_for_user(uid)
    assert not any(g.permission_key == "events.view" for g in grants)


async def test_a_not_yet_valid_grant_is_not_effective(s: AsyncSession) -> None:
    uid, rid = await _user_and_role(s, "events.view")
    now = _dt.datetime.now(_dt.UTC)
    await s.rollback()
    async with s.begin():
        ur = await s.get(UserRole, (uid, rid))
        assert ur is not None
        ur.valid_from = now + _dt.timedelta(days=1)

    grants = await SqlAlchemyGrantStore(s).grants_for_user(uid)
    assert not any(g.permission_key == "events.view" for g in grants)


async def test_an_open_window_grant_is_effective(s: AsyncSession) -> None:
    uid, _ = await _user_and_role(s, "events.view")
    grants = await SqlAlchemyGrantStore(s).grants_for_user(uid)
    assert any(g.permission_key == "events.view" for g in grants)


# --- delegation ----------------------------------------------------


async def test_delegation_grants_then_expires(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.delegation import DelegationService

    giver, _ = await _user_and_role(s, "events.takeover")
    getter = await _plain_user(s, "getter")

    await DelegationService(s).delegate(
        from_user_id=giver,
        to_user_id=getter,
        permission_key="events.takeover",
        expires_at=_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=1),
        actor_id=giver,
    )
    assert (
        await PermissionService(SqlAlchemyGrantStore(s)).authorize(getter, "events.takeover")
        is True
    )
    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "PERMISSION_DELEGATED")
        )
    ).scalar_one() == 1

    # expire it
    await s.rollback()
    async with s.begin():
        d = (await s.execute(select(PermissionDelegation))).scalar_one()
        d.expires_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(minutes=1)
    assert (
        await PermissionService(SqlAlchemyGrantStore(s)).authorize(getter, "events.takeover")
        is False
    )


async def test_revoke_is_immediate_and_audited(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.delegation import DelegationService

    giver, _ = await _user_and_role(s, "events.takeover")
    getter = await _plain_user(s, "getter")
    view = await DelegationService(s).delegate(
        from_user_id=giver,
        to_user_id=getter,
        permission_key="events.takeover",
        expires_at=_dt.datetime.now(_dt.UTC) + _dt.timedelta(days=1),
        actor_id=giver,
    )
    await DelegationService(s).revoke(view.id, actor_id=giver)
    assert (
        await PermissionService(SqlAlchemyGrantStore(s)).authorize(getter, "events.takeover")
        is False
    )
    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "PERMISSION_DELEGATION_REVOKED")
        )
    ).scalar_one() == 1


async def test_cannot_delegate_a_permission_you_lack(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.delegation import DelegationService, NotDelegatorsToGive

    giver = await _plain_user(s, "giver")  # holds nothing
    getter = await _plain_user(s, "getter")
    with pytest.raises(NotDelegatorsToGive):
        await DelegationService(s).delegate(
            from_user_id=giver,
            to_user_id=getter,
            permission_key="events.takeover",
            expires_at=_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=1),
        )


# --- API ---------------------------------------------------------


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def test_delegation_api_is_gated_and_validated(env: tuple) -> None:
    client, s = env
    os.environ["BBZ_MFA_STEPUP_PERMISSIONS"] = "[]"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    admin = await _admin(s, ["permissions.manage", "roles.manage", "events.takeover"])
    getter = await _plain_user(s, "getter")
    await _login(client, "admin")

    ok = await client.post(
        "/api/v1/permissions/delegations",
        json={
            "to_user_id": str(getter),
            "permission_key": "events.takeover",
            "expires_at": (_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=2)).isoformat(),
        },
    )
    assert ok.status_code == 201, ok.text
    did = ok.json()["id"]
    assert ok.json()["active"] is True

    # unknown permission → 422
    bad = await client.post(
        "/api/v1/permissions/delegations",
        json={
            "to_user_id": str(getter),
            "permission_key": "nope.nope",
            "expires_at": (_dt.datetime.now(_dt.UTC) + _dt.timedelta(hours=2)).isoformat(),
        },
    )
    assert bad.status_code == 422

    listed = (await client.get("/api/v1/permissions/delegations")).json()["delegations"]
    assert len(listed) == 1
    assert (await client.delete(f"/api/v1/permissions/delegations/{did}")).status_code == 204
    _ = admin


async def test_conditional_permission_write_rejects_a_bad_expression(env: tuple) -> None:
    client, s = env
    os.environ["BBZ_MFA_STEPUP_PERMISSIONS"] = "[]"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    await _admin(s, ["permissions.manage"])
    await s.rollback()
    async with s.begin():
        s.add(Role(key="ops", name="Ops"))
    await _login(client, "admin")
    role_id = str((await s.execute(select(Role.id).where(Role.key == "ops"))).scalar_one())

    r = await client.put(
        f"/api/v1/roles/{role_id}/permissions",
        json=[
            {
                "permission_key": "events.view",
                "scope": "global",
                "condition": {"op": "eq", "args": [{"field": "no_such_field"}, "x"]},
            }
        ],
    )
    assert r.status_code == 422


async def test_role_assignment_validity_window_via_api(env: tuple) -> None:
    client, s = env
    os.environ["BBZ_MFA_STEPUP_PERMISSIONS"] = "[]"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    await _admin(s, ["roles.manage", "roles.view"])
    target = await _plain_user(s, "target")
    await s.rollback()
    async with s.begin():
        s.add(Role(key="temp", name="Temp"))
    await _login(client, "admin")
    role_id = str((await s.execute(select(Role.id).where(Role.key == "temp"))).scalar_one())

    now = _dt.datetime.now(_dt.UTC)
    bad = await client.post(
        f"/api/v1/users/{target}/roles",
        json={
            "role_id": role_id,
            "valid_from": now.isoformat(),
            "valid_to": (now - _dt.timedelta(hours=1)).isoformat(),
        },
    )
    assert bad.status_code == 422

    ok = await client.post(
        f"/api/v1/users/{target}/roles",
        json={"role_id": role_id, "valid_to": (now + _dt.timedelta(days=7)).isoformat()},
    )
    assert ok.status_code == 204
    await s.rollback()
    ur = (await s.execute(select(UserRole).where(UserRole.user_id == target))).scalar_one()
    assert ur.valid_to is not None


# --- helpers ---------------------------------------------------------


async def _plain_user(s: AsyncSession, username: str) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        u = User(display_name=username.title())
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider="local", subject=username))
        return u.id


async def _user_and_role(s: AsyncSession, perm_key: str) -> tuple[uuid.UUID, uuid.UUID]:
    await s.rollback()
    async with s.begin():
        u = User(display_name="U")
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider="local", subject=f"u-{u.id.hex[:8]}"))
        r = Role(key=f"r-{u.id.hex[:8]}", name="R")
        s.add(r)
        await s.flush()
        p = (
            await s.execute(select(Permission).where(Permission.key == perm_key))
        ).scalar_one_or_none()
        if p is None:
            p = Permission(key=perm_key, area=perm_key.split(".")[0])
            s.add(p)
            await s.flush()
        s.add(RolePermission(role_id=r.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=r.id))
        return u.id, r.id


async def _user_with_conditional_perm(s: AsyncSession, perm_key: str, condition: dict) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        u = User(display_name="C")
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider="local", subject=f"c-{u.id.hex[:8]}"))
        r = Role(key=f"cr-{u.id.hex[:8]}", name="CR")
        s.add(r)
        await s.flush()
        p = (
            await s.execute(select(Permission).where(Permission.key == perm_key))
        ).scalar_one_or_none()
        if p is None:
            p = Permission(key=perm_key, area=perm_key.split(".")[0])
            s.add(p)
            await s.flush()
        s.add(RolePermission(role_id=r.id, permission_id=p.id, scope="global", condition=condition))
        s.add(UserRole(user_id=u.id, role_id=r.id))
        return u.id


async def _admin(s: AsyncSession, perms: list[str]) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password

    await s.rollback()
    async with s.begin():
        u = User(display_name="Admin")
        s.add(u)
        await s.flush()
        ident = AuthIdentity(user_id=u.id, provider="local", subject="admin")
        s.add(ident)
        await s.flush()
        s.add(LocalCredential(auth_identity_id=ident.id, password_hash=hash_password(_PW)))
        role = Role(key="r-admin", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            p = (
                await s.execute(select(Permission).where(Permission.key == key))
            ).scalar_one_or_none()
            if p is None:
                p = Permission(key=key, area=key.split(".")[0])
                s.add(p)
                await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
        return u.id


async def _login(c: httpx.AsyncClient, username: str) -> None:
    r = await c.post("/api/v1/auth/login", json={"username": username, "password": _PW})
    assert r.status_code == 200, r.text
