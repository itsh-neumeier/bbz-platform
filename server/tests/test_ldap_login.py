"""LDAP / AD bind authentication (roadmap E21-03).

Integration tests against the ``bbz-e14-ldap`` OpenLDAP container on the shared
docker network (seed: ``disp1`` / ``sicht1`` in
``ou=people,dc=bbz,dc=test``, groups ``leitstelle-disponenten`` /
``leitstelle-sichtleiter``). Skipped when that server is unreachable.
"""

from __future__ import annotations

import os
import socket
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.auth.ldap import LdapAuthFailed, LdapClient, LdapConfig, LdapInsecureError
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.auth_mapping import AuthGroupMapping
from bbz_core.infra.models.identity import AuthIdentity, User
from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

_HOST = os.environ.get("BBZ_TEST_LDAP_HOST", "bbz-e14-ldap")
_PORT = 389
_URL = f"ldap://{_HOST}:{_PORT}"
_BASE = "dc=bbz,dc=test"
_SVC_DN = f"cn=admin,{_BASE}"
_SVC_PW = "adminpass"


def _ldap_up() -> bool:
    try:
        with socket.create_connection((_HOST, _PORT), timeout=2):
            return True
    except OSError:
        return False


if not _ldap_up():  # pragma: no cover
    pytest.skip("no test LDAP server reachable", allow_module_level=True)


def _cfg(**over: object) -> LdapConfig:
    base = {
        "urls": (_URL,),
        "bind_dn": _SVC_DN,
        "bind_password": _SVC_PW,
        "user_search_base": f"ou=people,{_BASE}",
        "user_filter": "(uid=%s)",
        "group_search_base": f"ou=groups,{_BASE}",
        "start_tls": True,
        "tls_verify": False,
    }
    base.update(over)
    return LdapConfig(**base)  # type: ignore[arg-type]


# --- the client (against the real directory) --------------------------


def test_bind_auth_returns_the_principal_and_groups() -> None:
    p = LdapClient(_cfg()).authenticate("disp1", "Disp1-secret!")
    assert p.uid == "disp1" and p.dn == f"uid=disp1,ou=people,{_BASE}"
    assert p.email == "disp1@leitstelle.test"
    assert set(p.groups) == {"leitstelle-disponenten"}


def test_wrong_password_is_ldap_auth_failed() -> None:
    with pytest.raises(LdapAuthFailed):
        LdapClient(_cfg()).authenticate("disp1", "wrong")


def test_unknown_user_is_ldap_auth_failed() -> None:
    with pytest.raises(LdapAuthFailed):
        LdapClient(_cfg()).authenticate("ghost", "whatever")


def test_a_plaintext_url_without_starttls_is_refused() -> None:
    with pytest.raises(LdapInsecureError):
        LdapClient(_cfg(start_tls=False)).authenticate("disp1", "Disp1-secret!")


def test_starttls_is_negotiated_before_the_bind() -> None:
    # tls_verify off but StartTLS on — the transport is still encrypted
    p = LdapClient(_cfg(start_tls=True)).authenticate("sicht1", "Sicht1-secret!")
    assert set(p.groups) == {"leitstelle-disponenten", "leitstelle-sichtleiter"}


# --- LdapLoginService (DB + directory) -------------------------------


@pytest.fixture(autouse=True)
def _ldap_env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ.update(
        {
            "BBZ_LDAP_URL": _URL,
            "BBZ_LDAP_BIND_DN": _SVC_DN,
            "BBZ_LDAP_BIND_PASSWORD": _SVC_PW,
            "BBZ_LDAP_USER_SEARCH_BASE": f"ou=people,{_BASE}",
            "BBZ_LDAP_GROUP_SEARCH_BASE": f"ou=groups,{_BASE}",
            "BBZ_LDAP_TLS_VERIFY": "false",
            "BBZ_AUTH_PROVIDERS": '["local","ldap_ad"]',
            "BBZ_JWT_SECRET": "ldap-test-secret-at-least-32-bytes-long!!",
            "BBZ_ARGON2_MEMORY_COST_KIB": "512",
            "BBZ_ARGON2_TIME_COST": "1",
            "BBZ_SESSION_COOKIE_SECURE": "false",
        }
    )
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    for k in (
        "BBZ_LDAP_URL",
        "BBZ_LDAP_BIND_DN",
        "BBZ_LDAP_BIND_PASSWORD",
        "BBZ_LDAP_USER_SEARCH_BASE",
        "BBZ_LDAP_GROUP_SEARCH_BASE",
        "BBZ_LDAP_TLS_VERIFY",
        "BBZ_LDAP_JIT_PROVISIONING",
        "BBZ_AUTH_PROVIDERS",
    ):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _role(s: AsyncSession, key: str) -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        r = Role(key=key, name=key.title())
        s.add(r)
        await s.flush()
        p = Permission(key=f"{key}.view", area=key)
        s.add(p)
        await s.flush()
        s.add(RolePermission(role_id=r.id, permission_id=p.id, scope="global"))
        rid = r.id
    return rid


async def _link(s: AsyncSession, uid: str, name: str = "Directory User") -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        u = User(display_name=name)
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider="ldap_ad", subject=uid))
        user_id = u.id
    return user_id


async def test_login_service_resolves_a_provisioned_directory_user(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.ldap_login import LdapLoginService

    uid = await _link(s, "disp1")
    got = await LdapLoginService(s).authenticate("disp1", "Disp1-secret!")
    assert got == uid
    await s.rollback()
    ok = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "LOGIN_SUCCEEDED"))
    ).scalar_one()
    assert ok.after == {"provider": "ldap_ad"}


async def test_login_service_reconciles_group_mapped_roles(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.ldap_login import LdapLoginService

    await _role(s, "disponent")
    uid = await _link(s, "disp1")
    await s.rollback()
    async with s.begin():
        s.add(
            AuthGroupMapping(
                provider="ldap_ad", external_group="leitstelle-disponenten", role_key="disponent"
            )
        )

    await LdapLoginService(s).authenticate("disp1", "Disp1-secret!")
    await s.rollback()
    roles = (
        await s.execute(
            select(Role.key).select_from(UserRole).join(Role).where(UserRole.user_id == uid)
        )
    ).scalars()
    assert set(roles) == {"disponent"}


async def test_an_unprovisioned_directory_user_is_rejected_unless_jit(s: AsyncSession) -> None:
    from bbz_core import settings as settings_mod
    from bbz_core.infra.repositories.ldap_login import LdapLoginService

    with pytest.raises(LdapAuthFailed):
        await LdapLoginService(s).authenticate("sicht1", "Sicht1-secret!")

    os.environ["BBZ_LDAP_JIT_PROVISIONING"] = "true"
    settings_mod.get_settings.cache_clear()
    uid = await LdapLoginService(s).authenticate("sicht1", "Sicht1-secret!")
    await s.rollback()
    ident = (
        await s.execute(select(AuthIdentity).where(AuthIdentity.subject == "sicht1"))
    ).scalar_one()
    assert ident.user_id == uid and ident.provider == "ldap_ad"


async def test_bad_directory_password_audits_a_failure(s: AsyncSession) -> None:
    from bbz_core.infra.repositories.ldap_login import LdapLoginService

    await _link(s, "disp1")
    with pytest.raises(LdapAuthFailed):
        await LdapLoginService(s).authenticate("disp1", "nope")
    await s.rollback()
    n = (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGIN_FAILED")
        )
    ).scalar_one()
    assert n == 1


# --- /login falls back to the directory ------------------------------


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def test_login_endpoint_authenticates_a_directory_user(env: tuple) -> None:
    client, s = env
    await _link(s, "disp1", "Dana")
    r = await client.post(
        "/api/v1/auth/login", json={"username": "disp1", "password": "Disp1-secret!"}
    )
    assert r.status_code == 200, r.text
    assert r.cookies.get("bbz_access")
    assert r.json()["user"]["display_name"] == "Dana"


async def test_login_endpoint_still_rejects_a_bad_directory_password(env: tuple) -> None:
    client, s = env
    await _link(s, "disp1")
    r = await client.post("/api/v1/auth/login", json={"username": "disp1", "password": "wrong"})
    assert r.status_code == 401


async def test_local_login_is_unaffected_by_the_ldap_fallback(env: tuple) -> None:
    client, s = env
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import LocalCredential

    await s.rollback()
    async with s.begin():
        u = User(display_name="Local")
        s.add(u)
        await s.flush()
        ident = AuthIdentity(user_id=u.id, provider="local", subject="localuser")
        s.add(ident)
        await s.flush()
        s.add(
            LocalCredential(
                auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x")
            )
        )

    r = await client.post(
        "/api/v1/auth/login", json={"username": "localuser", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200 and r.cookies.get("bbz_access")
