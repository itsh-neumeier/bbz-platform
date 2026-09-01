"""MFA policy engine + step-up (roadmap E21-05).

Role-based MFA requirement with a grace period, enforced at login; a small set
of sensitive permissions additionally need a *fresh* step-up verification.
"""

from __future__ import annotations

import datetime as _dt
import os
import time
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pyotp
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
from bbz_core.infra.models.mfa_policy import MfaPolicy
from bbz_core.infra.models.rbac import (
    Group,
    GroupRole,
    Permission,
    Role,
    RolePermission,
    UserGroup,
    UserRole,
)
from bbz_core.infra.models.session import Session
from bbz_core.infra.repositories.mfa_policy import MfaPolicyService, MfaRequirement

_PW = "Wolke7-Bahnhof!x"


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ.update(
        {
            "BBZ_ARGON2_MEMORY_COST_KIB": "512",
            "BBZ_ARGON2_TIME_COST": "1",
            "BBZ_JWT_SECRET": "mfa-policy-test-secret-at-least-32-bytes!!",
            "BBZ_SESSION_COOKIE_SECURE": "false",
            "BBZ_TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        }
    )
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    for k in (
        "BBZ_TOTP_ENCRYPTION_KEY",
        "BBZ_MFA_POLICY_ENFORCE_EXTERNAL",
        "BBZ_MFA_STEPUP_MAX_AGE_SECONDS",
        "BBZ_MFA_STEPUP_PERMISSIONS",
    ):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _user(
    s: AsyncSession,
    username: str,
    *,
    roles: list[str] | None = None,
    perms: list[str] | None = None,
    role_granted_days_ago: int = 0,
) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password

    await s.rollback()
    async with s.begin():
        u = User(display_name=username.title())
        s.add(u)
        await s.flush()
        ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
        s.add(ident)
        await s.flush()
        s.add(LocalCredential(auth_identity_id=ident.id, password_hash=hash_password(_PW)))
        granted = _dt.datetime.now(_dt.UTC) - _dt.timedelta(days=role_granted_days_ago)
        for key in roles or []:
            r = (await s.execute(select(Role).where(Role.key == key))).scalar_one_or_none()
            if r is None:
                r = Role(key=key, name=key.title())
                s.add(r)
                await s.flush()
            s.add(UserRole(user_id=u.id, role_id=r.id, granted_at=granted))
        if perms:
            r = Role(key=f"perm-{username}", name="P")
            s.add(r)
            await s.flush()
            for key in perms:
                p = (
                    await s.execute(select(Permission).where(Permission.key == key))
                ).scalar_one_or_none()
                if p is None:
                    p = Permission(key=key, area=key.split(".")[0])
                    s.add(p)
                    await s.flush()
                s.add(RolePermission(role_id=r.id, permission_id=p.id, scope="global"))
            s.add(UserRole(user_id=u.id, role_id=r.id, granted_at=granted))
        return u.id


async def _policy(s: AsyncSession, role_key: str, *, grace: int = 7) -> None:
    await s.rollback()
    async with s.begin():
        if (await s.execute(select(Role).where(Role.key == role_key))).scalar_one_or_none() is None:
            s.add(Role(key=role_key, name=role_key.title()))
            await s.flush()
        s.add(MfaPolicy(role_key=role_key, grace_period_days=grace))


async def _role(s: AsyncSession, key: str) -> None:
    await s.rollback()
    async with s.begin():
        if (await s.execute(select(Role).where(Role.key == key))).scalar_one_or_none() is None:
            s.add(Role(key=key, name=key.title()))


async def _login(
    client: httpx.AsyncClient, username: str, totp: str | None = None
) -> httpx.Response:
    body = {"username": username, "password": _PW}
    if totp:
        body["totp"] = totp
    return await client.post("/api/v1/auth/login", json=body)


async def _enrol(client: httpx.AsyncClient) -> str:
    enrol = (await client.post("/api/v1/auth/totp/enrol")).json()
    code = pyotp.TOTP(enrol["secret"]).now()
    assert (await client.post("/api/v1/auth/totp/activate", json={"code": code})).status_code == 204
    return enrol["secret"]


def _future_totp(secret: str) -> str:
    return pyotp.TOTP(secret).at((int(time.time() // 30) + 1) * 30 + 5)


# --- MfaPolicyService.evaluate ---------------------------------------------


async def test_no_policy_means_not_required(s: AsyncSession) -> None:
    uid = await _user(s, "u1", roles=["disponent"])
    req = await MfaPolicyService(s).evaluate(uid)
    assert req.required is False and req.blocks(satisfied=False) is False


async def test_a_policy_on_a_held_role_requires_mfa_after_grace(s: AsyncSession) -> None:
    uid = await _user(s, "u2", roles=["leitung"], role_granted_days_ago=30)
    await _policy(s, "leitung", grace=7)

    req = await MfaPolicyService(s).evaluate(uid)
    assert req.required and not req.in_grace
    assert req.blocks(satisfied=False) and not req.blocks(satisfied=True)


async def test_a_fresh_assignment_is_still_in_grace(s: AsyncSession) -> None:
    uid = await _user(s, "u3", roles=["leitung"], role_granted_days_ago=1)
    await _policy(s, "leitung", grace=7)

    req = await MfaPolicyService(s).evaluate(uid)
    assert req.required and req.in_grace and req.grace_until is not None
    assert not req.blocks(satisfied=False)  # grace not elapsed


async def test_a_group_derived_policy_role_counts(s: AsyncSession) -> None:
    uid = await _user(s, "u4")
    await _policy(s, "leitung", grace=0)
    await s.rollback()
    async with s.begin():
        g = Group(key="leitungsteam", name="Leitungsteam")
        s.add(g)
        await s.flush()
        role_id = (await s.execute(select(Role.id).where(Role.key == "leitung"))).scalar_one()
        s.add(GroupRole(group_id=g.id, role_id=role_id))
        s.add(UserGroup(user_id=uid, group_id=g.id))

    req = await MfaPolicyService(s).evaluate(uid)
    assert req.required and req.blocks(satisfied=False)  # grace 0


def test_requirement_blocks_logic() -> None:
    r = MfaRequirement(required=True, in_grace=False, grace_until=None)
    assert r.blocks(satisfied=False) and not r.blocks(satisfied=True)
    assert not MfaRequirement(True, True, None).blocks(satisfied=False)
    assert not MfaRequirement(False, False, None).blocks(satisfied=False)


# --- _enforce_mfa_policy external toggle ----------------------------------


async def test_external_enforcement_can_be_disabled(s: AsyncSession) -> None:
    from bbz_core import settings as settings_mod
    from bbz_core.api.v1.auth import _enforce_mfa_policy

    uid = await _user(s, "ext1", roles=["leitung"], role_granted_days_ago=30)
    await _policy(s, "leitung", grace=7)

    blocked = await _enforce_mfa_policy(s, uid, satisfied=False, external=True)
    assert blocked.blocked

    os.environ["BBZ_MFA_POLICY_ENFORCE_EXTERNAL"] = "false"
    settings_mod.get_settings.cache_clear()
    relaxed = await _enforce_mfa_policy(s, uid, satisfied=False, external=True)
    assert not relaxed.blocked


# --- login enforcement ---------------------------------------------------


async def test_login_blocked_when_mfa_required_and_grace_elapsed(env: tuple) -> None:
    client, s = env
    await _user(s, "late", roles=["leitung"], role_granted_days_ago=30)
    await _policy(s, "leitung", grace=7)

    r = await _login(client, "late")
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_required"
    await s.rollback()
    assert (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGIN_FAILED")
        )
    ).scalar_one() == 1


async def test_login_allowed_in_grace_with_an_enrolment_nudge(env: tuple) -> None:
    client, s = env
    await _user(s, "newish", roles=["leitung"], role_granted_days_ago=2)
    await _policy(s, "leitung", grace=7)

    r = await _login(client, "newish")
    assert r.status_code == 200
    body = r.json()
    assert body["mfa_enrolment_required"] is True and body["mfa_grace_until"] is not None


async def test_a_policy_user_who_enrolled_logs_in_normally(env: tuple) -> None:
    client, s = env
    await _user(s, "compliant", roles=["leitung"], role_granted_days_ago=2)
    await _policy(s, "leitung", grace=7)
    await _login(client, "compliant")  # still in grace → reaches enrolment
    secret = await _enrol(client)

    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with fresh:
        no_code = await _login(fresh, "compliant")
        assert no_code.status_code == 401 and no_code.json()["error"]["code"] == "totp_required"
        ok = await _login(fresh, "compliant", _future_totp(secret))
        assert ok.status_code == 200
        assert ok.json()["mfa_enrolment_required"] is False


# --- session.mfa_verified_at -------------------------------------------


async def test_a_totp_login_stamps_mfa_verified_at(env: tuple) -> None:
    client, s = env
    uid = await _user(s, "stamp")
    await _login(client, "stamp")
    secret = await _enrol(client)

    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with fresh:
        assert (await _login(fresh, "stamp", _future_totp(secret))).status_code == 200

    await s.rollback()
    rows = (
        (
            await s.execute(
                select(Session).where(Session.user_id == uid).order_by(Session.created_at)
            )
        )
        .scalars()
        .all()
    )
    assert rows[0].mfa_verified_at is None  # the first, password-only login
    assert rows[-1].mfa_verified_at is not None  # the TOTP login


# --- step-up ---------------------------------------------------------


async def _admin(s: AsyncSession, perms: list[str]) -> None:
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
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))


async def test_stepup_blocks_a_stale_session_then_a_stepup_unblocks_it(env: tuple) -> None:
    client, s = env
    await _admin(s, ["permissions.manage"])
    await _role(s, "leitung")
    await _login(client, "admin")  # password only → no fresh MFA
    secret = await _enrol(client)

    # the PUT is require_stepup("permissions.manage") — stale session → 401
    blocked = await client.put("/api/v1/auth/mfa-policies/leitung", json={"grace_period_days": 3})
    assert blocked.status_code == 401 and blocked.json()["error"]["code"] == "step_up_required"
    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "MFA_STEPUP_REQUIRED")
        )
    ).scalar_one() == 1

    # step up, then retry
    su = await client.post("/api/v1/auth/mfa-policies/step-up", json={"totp": _future_totp(secret)})
    assert su.status_code == 204
    ok = await client.put("/api/v1/auth/mfa-policies/leitung", json={"grace_period_days": 3})
    assert ok.status_code == 200


async def test_a_totp_login_is_fresh_enough_for_stepup(env: tuple) -> None:
    client, s = env
    await _admin(s, ["permissions.manage"])
    await _role(s, "leitung")
    await _login(client, "admin")
    secret = await _enrol(client)

    fresh = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with fresh:
        assert (await _login(fresh, "admin", _future_totp(secret))).status_code == 200
        r = await fresh.put("/api/v1/auth/mfa-policies/leitung", json={"grace_period_days": 5})
        assert r.status_code == 200  # login's own MFA counts as the step-up


async def test_stepup_expires(env: tuple) -> None:
    client, s = env
    os.environ["BBZ_MFA_STEPUP_MAX_AGE_SECONDS"] = "0"  # everything is "too old"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    await _admin(s, ["permissions.manage"])
    await _role(s, "leitung")
    await _login(client, "admin")
    secret = await _enrol(client)
    await client.post("/api/v1/auth/mfa-policies/step-up", json={"totp": _future_totp(secret)})

    r = await client.put("/api/v1/auth/mfa-policies/leitung", json={"grace_period_days": 1})
    assert r.status_code == 401 and r.json()["error"]["code"] == "step_up_required"


# --- admin CRUD ------------------------------------------------------


async def test_policy_crud_is_gated_and_audited(env: tuple) -> None:
    client, s = env
    os.environ["BBZ_MFA_STEPUP_PERMISSIONS"] = "[]"  # isolate CRUD from step-up here
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    await _admin(s, ["permissions.manage"])
    await s.rollback()
    async with s.begin():
        s.add(Role(key="disponent", name="Disponent"))
    await _login(client, "admin")

    created = await client.put(
        "/api/v1/auth/mfa-policies/disponent", json={"grace_period_days": 14}
    )
    assert created.status_code == 200 and created.json()["grace_period_days"] == 14

    listed = (await client.get("/api/v1/auth/mfa-policies")).json()["policies"]
    assert listed == [{"role_key": "disponent", "grace_period_days": 14}]

    updated = await client.put("/api/v1/auth/mfa-policies/disponent", json={"grace_period_days": 3})
    assert updated.json()["grace_period_days"] == 3

    unknown = await client.put("/api/v1/auth/mfa-policies/ghost", json={"grace_period_days": 1})
    assert unknown.status_code == 422

    assert (await client.delete("/api/v1/auth/mfa-policies/disponent")).status_code == 204
    assert (await client.delete("/api/v1/auth/mfa-policies/disponent")).status_code == 404

    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "MFA_POLICY_CHANGED")
        )
    ).scalar_one()
    assert n == 3  # create + update + delete


async def test_policy_write_needs_permissions_manage(env: tuple) -> None:
    client, s = env
    os.environ["BBZ_MFA_STEPUP_PERMISSIONS"] = "[]"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    await _admin(s, ["roles.view"])
    await _login(client, "admin")
    r = await client.put("/api/v1/auth/mfa-policies/x", json={"grace_period_days": 1})
    assert r.status_code == 403
