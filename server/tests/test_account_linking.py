"""Account linking + auth-provider config (roadmap E21-08)."""

from __future__ import annotations

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
from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

_PW = "Wolke7-Bahnhof!x"


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ.update(
        {
            "BBZ_ARGON2_MEMORY_COST_KIB": "512",
            "BBZ_ARGON2_TIME_COST": "1",
            "BBZ_JWT_SECRET": "linking-test-secret-at-least-32-bytes!!",
            "BBZ_SESSION_COOKIE_SECURE": "false",
            "BBZ_TOTP_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "BBZ_MFA_STEPUP_PERMISSIONS": "[]",
        }
    )
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    for k in (
        "BBZ_TOTP_ENCRYPTION_KEY",
        "BBZ_MFA_STEPUP_PERMISSIONS",
        "BBZ_MFA_STEPUP_MAX_AGE_SECONDS",
    ):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _local_user(s: AsyncSession, username: str, *, admin: bool = False) -> uuid.UUID:
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
        if admin:
            role = (
                await s.execute(select(Role).where(Role.key == "administrator"))
            ).scalar_one_or_none()
            if role is None:
                role = Role(key="administrator", name="Administrator")
                s.add(role)
                await s.flush()
                p = Permission(key="permissions.manage", area="permissions")
                s.add(p)
                await s.flush()
                s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
            s.add(UserRole(user_id=u.id, role_id=role.id))
        return u.id


async def _ext_identity(s: AsyncSession, user_id: uuid.UUID, provider: str, subject: str) -> None:
    await s.rollback()
    async with s.begin():
        s.add(AuthIdentity(user_id=user_id, provider=provider, subject=subject))


async def _login(c: httpx.AsyncClient, username: str) -> None:
    r = await c.post("/api/v1/auth/login", json={"username": username, "password": _PW})
    assert r.status_code == 200, r.text


async def _session_as(c: httpx.AsyncClient, s: AsyncSession, user_id: uuid.UUID) -> None:
    """Attach the session + CSRF cookies for a user who may have no local password."""
    from bbz_core.auth.csrf import issue_csrf_token
    from bbz_core.auth.sessions import SessionService
    from bbz_core.infra.repositories.sessions import SqlAlchemySessionStore

    await s.rollback()
    tokens = await SessionService(SqlAlchemySessionStore(s)).start(user_id)
    c.cookies.set("bbz_access", tokens.access_token)
    c.cookies.set("bbz_csrf", issue_csrf_token(tokens.session_id))  # conftest mirrors it


async def _external_only(s: AsyncSession, username: str, provider: str = "ldap_ad") -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        u = User(display_name=username.title())
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider=provider, subject=username))
        return u.id


# --- list ------------------------------------------------------------


async def test_list_shows_the_callers_identities(env: tuple) -> None:
    c, s = env
    uid = await _local_user(s, "alice")
    await _ext_identity(s, uid, "entra_oidc", "sub-alice")
    await _login(c, "alice")

    got = (await c.get("/api/v1/auth/identities")).json()["identities"]
    assert {i["provider"] for i in got} == {"local", "entra_oidc"}


# --- link local ----------------------------------------------------


async def test_link_a_local_password_to_an_external_only_account(env: tuple) -> None:
    c, s = env
    uid = await _external_only(s, "diruser")
    await _session_as(c, s, uid)

    r = await c.post(
        "/api/v1/auth/identities/local", json={"username": "diruser-local", "password": _PW}
    )
    assert r.status_code == 201, r.text
    # now a local login works
    fresh = httpx.AsyncClient(transport=c._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    async with fresh:
        lg = await fresh.post(
            "/api/v1/auth/login", json={"username": "diruser-local", "password": _PW}
        )
        assert lg.status_code == 200
    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "IDENTITY_LINKED")
        )
    ).scalar_one()
    assert n == 1


async def test_link_local_rejects_a_weak_password(env: tuple) -> None:
    c, s = env
    uid = await _external_only(s, "weakling")
    await _session_as(c, s, uid)
    r = await c.post(
        "/api/v1/auth/identities/local", json={"username": "weakling-local", "password": "weak"}
    )
    assert r.status_code == 422


async def test_cannot_link_local_twice(env: tuple) -> None:
    c, s = env
    await _local_user(s, "carol")
    await _login(c, "carol")
    r = await c.post("/api/v1/auth/identities/local", json={"username": "carol2", "password": _PW})
    assert r.status_code == 409  # already has a local identity


# --- unlink guards -----------------------------------------------


async def test_cannot_unlink_the_only_identity(env: tuple) -> None:
    c, s = env
    await _local_user(s, "dave")
    await _login(c, "dave")
    ids = (await c.get("/api/v1/auth/identities")).json()["identities"]
    r = await c.delete(f"/api/v1/auth/identities/{ids[0]['id']}")
    assert r.status_code == 409


async def test_unlink_a_secondary_identity(env: tuple) -> None:
    c, s = env
    uid = await _local_user(s, "erin")
    await _ext_identity(s, uid, "entra_oidc", "sub-erin")
    await _login(c, "erin")

    ids = (await c.get("/api/v1/auth/identities")).json()["identities"]
    ext = next(i for i in ids if i["provider"] == "entra_oidc")
    assert (await c.delete(f"/api/v1/auth/identities/{ext['id']}")).status_code == 204
    remaining = (await c.get("/api/v1/auth/identities")).json()["identities"]
    assert [i["provider"] for i in remaining] == ["local"]

    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "IDENTITY_UNLINKED")
        )
    ).scalar_one()
    assert n == 1


async def test_cannot_strip_the_last_admins_sign_in_methods(env: tuple) -> None:
    c, s = env
    admin = await _local_user(s, "admin", admin=True)
    await _ext_identity(s, admin, "entra_oidc", "sub-admin")
    await _login(c, "admin")

    ids = (await c.get("/api/v1/auth/identities")).json()["identities"]
    ext = next(i for i in ids if i["provider"] == "entra_oidc")
    r = await c.delete(f"/api/v1/auth/identities/{ext['id']}")
    assert r.status_code == 409  # last active admin


# --- second-factor confirmation -------------------------------


async def test_link_requires_a_fresh_second_factor_when_the_account_has_one(env: tuple) -> None:
    c, s = env
    uid = await _local_user(s, "fred")
    await _ext_identity(s, uid, "ldap_ad", "fred-dir")
    await _login(c, "fred")

    enrol = (await c.post("/api/v1/auth/totp/enrol")).json()
    await c.post("/api/v1/auth/totp/activate", json={"code": pyotp.TOTP(enrol["secret"]).now()})

    # a plain (password-only) session is not "fresh MFA" → step-up required to unlink
    ids = (await c.get("/api/v1/auth/identities")).json()["identities"]
    ext = next(i for i in ids if i["provider"] == "ldap_ad")
    blocked = await c.delete(f"/api/v1/auth/identities/{ext['id']}")
    assert blocked.status_code == 401 and blocked.json()["error"]["code"] == "step_up_required"

    su = await c.post(
        "/api/v1/auth/mfa-policies/step-up",
        json={"totp": pyotp.TOTP(enrol["secret"]).at((int(time.time() // 30) + 1) * 30 + 5)},
    )
    assert su.status_code == 204
    assert (await c.delete(f"/api/v1/auth/identities/{ext['id']}")).status_code == 204


# --- provider config ------------------------------------------


async def test_provider_config_crud_is_gated_and_audited(env: tuple) -> None:
    c, s = env
    await _local_user(s, "admin", admin=True)
    await _login(c, "admin")

    listed = (await c.get("/api/v1/auth/providers")).json()["providers"]
    assert {p["provider"] for p in listed} == {"local", "entra_oidc", "ldap_ad"}
    assert next(p for p in listed if p["provider"] == "local")["env_configured"] is True

    r = await c.put(
        "/api/v1/auth/providers/ldap_ad", json={"enabled": False, "display_name": "Firmen-AD"}
    )
    assert r.status_code == 200 and r.json()["enabled"] is False

    again = (await c.get("/api/v1/auth/providers")).json()["providers"]
    assert next(p for p in again if p["provider"] == "ldap_ad")["display_name"] == "Firmen-AD"

    unknown = await c.put("/api/v1/auth/providers/nope", json={"enabled": True})
    assert unknown.status_code == 422

    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "AUTH_PROVIDER_CONFIGURED")
        )
    ).scalar_one()
    assert n == 1


async def test_provider_config_needs_permissions_manage(env: tuple) -> None:
    c, s = env
    await _local_user(s, "plain")
    await _login(c, "plain")
    assert (await c.get("/api/v1/auth/providers")).status_code == 403


# --- OIDC link flow (stubbed) --------------------------------


async def test_oidc_link_attaches_the_verified_subject(env: tuple, monkeypatch) -> None:
    c, s = env
    uid = await _local_user(s, "grace")
    await _login(c, "grace")

    from bbz_core.infra.repositories import oidc_login as oidc_mod

    async def _fake_complete_link(self, provider, *, code, state):
        return uid, "entra-sub-grace"

    monkeypatch.setattr(oidc_mod.OidcLoginService, "complete_link", _fake_complete_link)
    r = await c.post(
        "/api/v1/auth/identities/oidc/entra_oidc/callback", json={"code": "x", "state": "y"}
    )
    assert r.status_code == 204
    await s.rollback()
    linked = (
        await s.execute(
            select(AuthIdentity).where(
                AuthIdentity.user_id == uid, AuthIdentity.provider == "entra_oidc"
            )
        )
    ).scalar_one()
    assert linked.subject == "entra-sub-grace"


async def test_oidc_link_rejects_a_flow_for_another_user(env: tuple, monkeypatch) -> None:
    c, s = env
    await _local_user(s, "heidi")
    await _login(c, "heidi")

    from bbz_core.infra.repositories import oidc_login as oidc_mod

    async def _fake_complete_link(self, provider, *, code, state):
        return uuid.uuid4(), "someone-else"  # a different link_user_id

    monkeypatch.setattr(oidc_mod.OidcLoginService, "complete_link", _fake_complete_link)
    r = await c.post(
        "/api/v1/auth/identities/oidc/entra_oidc/callback", json={"code": "x", "state": "y"}
    )
    assert r.status_code == 401
