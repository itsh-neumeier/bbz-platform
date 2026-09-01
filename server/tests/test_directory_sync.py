"""Directory sync — reconcile BBZ against the directory (roadmap E21-04).

Most tests drive :class:`DirectorySyncService` with a fake enumerator (no network
/ container needed). Two tests at the end exercise the real ``ldap3``
``enumerate_principals`` against the ``bbz-e14-ldap`` container and are skipped
when it is unreachable.
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

from bbz_core.auth.ldap import LdapPrincipal, LdapUnavailableError
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.auth_mapping import AuthGroupMapping
from bbz_core.infra.models.directory_sync import DirectorySyncState
from bbz_core.infra.models.identity import AuthIdentity, User, UserStatus
from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole
from bbz_core.infra.models.session import Session
from bbz_core.infra.repositories.directory_sync import DirectorySyncService


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ.update(
        {
            "BBZ_LDAP_URL": "ldaps://directory.invalid:636",
            "BBZ_LDAP_BIND_DN": "cn=svc,dc=bbz,dc=test",
            "BBZ_LDAP_BIND_PASSWORD": "x",
            "BBZ_LDAP_USER_SEARCH_BASE": "ou=people,dc=bbz,dc=test",
            "BBZ_LDAP_GROUP_SEARCH_BASE": "ou=groups,dc=bbz,dc=test",
            "BBZ_JWT_SECRET": "dirsync-test-secret-at-least-32-bytes!!",
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
        "BBZ_LDAP_SYNC_ENABLED",
        "BBZ_LDAP_SYNC_PROVISION",
        "BBZ_LDAP_SYNC_MAX_DEACTIVATIONS",
        "BBZ_LDAP_SYNC_INTERVAL_SECONDS",
        "BBZ_OIDC_JIT_DEFAULT_ROLE",
    ):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


class _FakeLdap:
    def __init__(self, *principals: LdapPrincipal) -> None:
        self._principals = list(principals)

    def enumerate_principals(self) -> list[LdapPrincipal]:
        return list(self._principals)


class _BoomLdap:
    def enumerate_principals(self) -> list[LdapPrincipal]:
        raise LdapUnavailableError("no server answered")


def _p(uid: str, *groups: str, name: str | None = None, mail: str | None = None) -> LdapPrincipal:
    return LdapPrincipal(
        dn=f"uid={uid},ou=people,dc=bbz,dc=test",
        uid=uid,
        display_name=name or uid.title(),
        email=mail,
        groups=tuple(groups),
    )


async def _dir_user(s: AsyncSession, uid: str, *, name: str = "Old Name") -> uuid.UUID:
    await s.rollback()
    async with s.begin():
        u = User(display_name=name)
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider="ldap_ad", subject=uid))
        return u.id


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
        return r.id


async def _user_role_keys(s: AsyncSession, user_id: uuid.UUID) -> set[str]:
    await s.rollback()
    rows = await s.execute(
        select(Role.key).select_from(UserRole).join(Role).where(UserRole.user_id == user_id)
    )
    return set(rows.scalars())


# --- provisioning ---------------------------------------------------------


async def test_a_new_directory_account_is_provisioned(s: AsyncSession) -> None:
    svc = DirectorySyncService(s, client=_FakeLdap(_p("newbie", name="New Bie", mail="n@b.test")))
    report = await svc.run()

    assert report.ok and report.created == 1 and report.created_uids == ["newbie"]
    await s.rollback()
    ident = (
        await s.execute(select(AuthIdentity).where(AuthIdentity.subject == "newbie"))
    ).scalar_one()
    assert ident.provider == "ldap_ad"
    user = await s.get(User, ident.user_id)
    assert user is not None and user.display_name == "New Bie"


async def test_provisioning_can_be_disabled(s: AsyncSession) -> None:
    os.environ["BBZ_LDAP_SYNC_PROVISION"] = "false"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    report = await DirectorySyncService(s, client=_FakeLdap(_p("newbie"))).run()
    assert report.created == 0
    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(AuthIdentity))).scalar_one() == 0


async def test_a_new_account_gets_the_jit_default_role(s: AsyncSession) -> None:
    await _role(s, "disponent")
    os.environ["BBZ_OIDC_JIT_DEFAULT_ROLE"] = "disponent"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    await DirectorySyncService(s, client=_FakeLdap(_p("newbie"))).run()
    await s.rollback()
    ident = (
        await s.execute(select(AuthIdentity).where(AuthIdentity.subject == "newbie"))
    ).scalar_one()
    assert await _user_role_keys(s, ident.user_id) == {"disponent"}


# --- deactivation --------------------------------------------------------


async def test_a_vanished_account_is_soft_deactivated_and_sessions_revoked(s: AsyncSession) -> None:
    import datetime as _dt

    uid = await _dir_user(s, "ghost")
    async with s.begin():
        s.add(
            Session(
                user_id=uid,
                refresh_token_hash="ghost-rt",
                expires_at=_dt.datetime.now(_dt.UTC) + _dt.timedelta(days=1),
            )
        )

    report = await DirectorySyncService(s, client=_FakeLdap(_p("someone-else"))).run()

    assert report.deactivated == 1 and report.deactivated_uids == ["ghost"]
    await s.rollback()
    user = await s.get(User, uid)
    assert user is not None and user.status == UserStatus.DISABLED.value  # soft — row still there
    live = (
        await s.execute(
            select(func.count())
            .select_from(Session)
            .where(Session.user_id == uid, Session.revoked_at.is_(None))
        )
    ).scalar_one()
    assert live == 0
    audited = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "USER_DEACTIVATED"))
    ).scalar_one()
    assert audited.target_id == str(uid)


async def test_an_already_disabled_vanished_account_is_left_alone(s: AsyncSession) -> None:
    uid = await _dir_user(s, "ghost")
    async with s.begin():
        u = await s.get(User, uid)
        assert u is not None
        u.status = UserStatus.DISABLED.value

    report = await DirectorySyncService(s, client=_FakeLdap(_p("other"))).run()
    assert report.deactivated == 0


async def test_the_deactivation_cap_aborts_the_run(s: AsyncSession) -> None:
    for i in range(3):
        await _dir_user(s, f"ghost{i}")
    os.environ["BBZ_LDAP_SYNC_MAX_DEACTIVATIONS"] = "2"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    report = await DirectorySyncService(s, client=_FakeLdap(_p("still-here"))).run()

    assert not report.ok and report.aborted and report.deactivated == 0
    await s.rollback()
    disabled = (
        await s.execute(
            select(func.count()).select_from(User).where(User.status == UserStatus.DISABLED.value)
        )
    ).scalar_one()
    assert disabled == 0


async def test_force_overrides_the_deactivation_cap(s: AsyncSession) -> None:
    for i in range(3):
        await _dir_user(s, f"ghost{i}")
    os.environ["BBZ_LDAP_SYNC_MAX_DEACTIVATIONS"] = "2"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()

    report = await DirectorySyncService(s, client=_FakeLdap(_p("still-here"))).run(force=True)
    assert report.ok and report.deactivated == 3


# --- an empty / unreachable directory is an error, not "everyone left" ---


async def test_an_empty_directory_result_aborts(s: AsyncSession) -> None:
    await _dir_user(s, "ghost")
    report = await DirectorySyncService(s, client=_FakeLdap()).run()
    assert not report.ok and report.deactivated == 0
    await s.rollback()
    st = (
        await s.execute(select(DirectorySyncState).where(DirectorySyncState.source == "ldap_ad"))
    ).scalar_one()
    assert st.last_error is not None and st.last_success_at is None


async def test_a_directory_error_is_recorded_not_raised(s: AsyncSession) -> None:
    report = await DirectorySyncService(s, client=_BoomLdap()).run()
    assert not report.ok and "LdapUnavailableError" in (report.error or "")


# --- group reconcile + profile refresh + isolation ----------------------


async def test_group_mapped_roles_are_reconciled_for_present_users(s: AsyncSession) -> None:
    await _role(s, "disponent")
    uid = await _dir_user(s, "disp1")
    await s.rollback()
    async with s.begin():
        s.add(
            AuthGroupMapping(
                provider="ldap_ad", external_group="leitstelle-disponenten", role_key="disponent"
            )
        )

    await DirectorySyncService(s, client=_FakeLdap(_p("disp1", "leitstelle-disponenten"))).run()
    assert await _user_role_keys(s, uid) == {"disponent"}

    # group removed in the directory → role reconciled away on the next run
    await DirectorySyncService(s, client=_FakeLdap(_p("disp1"))).run()
    assert await _user_role_keys(s, uid) == set()


async def test_a_changed_display_name_is_refreshed(s: AsyncSession) -> None:
    uid = await _dir_user(s, "disp1", name="Stale Name")
    await DirectorySyncService(s, client=_FakeLdap(_p("disp1", name="Fresh Name"))).run()
    await s.rollback()
    user = await s.get(User, uid)
    assert user is not None and user.display_name == "Fresh Name"


async def test_a_local_user_is_never_touched(s: AsyncSession) -> None:
    async with s.begin():
        u = User(display_name="Local Admin")
        s.add(u)
        await s.flush()
        s.add(AuthIdentity(user_id=u.id, provider="local", subject="admin"))
        local_id = u.id

    await DirectorySyncService(s, client=_FakeLdap(_p("someone"))).run()
    await s.rollback()
    user = await s.get(User, local_id)
    assert user is not None and user.status == UserStatus.ACTIVE.value


# --- dry run changes nothing -------------------------------------------


async def test_dry_run_computes_the_diff_but_writes_nothing(s: AsyncSession) -> None:
    ghost = await _dir_user(s, "ghost")

    report = await DirectorySyncService(s, client=_FakeLdap(_p("newbie"))).run(dry_run=True)

    assert report.dry_run
    assert report.created_uids == ["newbie"] and report.deactivated_uids == ["ghost"]
    await s.rollback()
    # no user created, ghost still active, no state row, no audit
    assert (await s.execute(select(func.count()).select_from(AuthIdentity))).scalar_one() == 1
    assert (await s.get(User, ghost)).status == UserStatus.ACTIVE.value  # type: ignore[union-attr]
    assert (await s.execute(select(func.count()).select_from(DirectorySyncState))).scalar_one() == 0
    assert (await s.execute(select(func.count()).select_from(AuditEvent))).scalar_one() == 0


# --- the completed audit + state row ----------------------------------


async def test_a_successful_run_audits_completion_and_records_state(s: AsyncSession) -> None:
    await _dir_user(s, "disp1")
    report = await DirectorySyncService(s, client=_FakeLdap(_p("disp1"), _p("newbie"))).run()

    await s.rollback()
    done = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "DIRECTORY_SYNC_COMPLETED"))
    ).scalar_one()
    assert done.after["scanned"] == 2 and done.after["created"] == 1
    st = (
        await s.execute(select(DirectorySyncState).where(DirectorySyncState.source == "ldap_ad"))
    ).scalar_one()
    assert st.last_success_at is not None and st.last_summary["scanned"] == 2
    assert report.ok


# --- the scheduled tick honours the interval --------------------------


async def test_the_tick_is_a_noop_within_the_interval(s: AsyncSession, monkeypatch) -> None:
    import datetime as _dt

    from bbz_core import settings as settings_mod
    from bbz_core.workers import registry

    os.environ["BBZ_LDAP_SYNC_ENABLED"] = "true"
    os.environ["BBZ_LDAP_SYNC_INTERVAL_SECONDS"] = "3600"
    settings_mod.get_settings.cache_clear()

    async with s.begin():
        s.add(DirectorySyncState(source="ldap_ad", last_run_at=_dt.datetime.now(_dt.UTC)))

    called = False

    async def _boom(self, **kw):  # pragma: no cover - must not run
        nonlocal called
        called = True
        raise AssertionError("sync ran inside the interval")

    monkeypatch.setattr(DirectorySyncService, "run", _boom)
    result = await registry._directory_sync_tick()
    assert result == 0 and called is False


# --- against the real OpenLDAP container ------------------------------

_LDAP_HOST = os.environ.get("BBZ_TEST_LDAP_HOST", "bbz-e14-ldap")


def _ldap_up() -> bool:
    try:
        with socket.create_connection((_LDAP_HOST, 389), timeout=2):
            return True
    except OSError:
        return False


_REAL = pytest.mark.skipif(not _ldap_up(), reason="no test LDAP server reachable")


@_REAL
async def test_enumerate_against_the_real_directory_provisions_both_seed_users(
    s: AsyncSession,
) -> None:
    from bbz_core.auth.ldap import LdapClient, LdapConfig

    cfg = LdapConfig(
        urls=(f"ldap://{_LDAP_HOST}:389",),
        bind_dn="cn=admin,dc=bbz,dc=test",
        bind_password="adminpass",
        user_search_base="ou=people,dc=bbz,dc=test",
        user_list_filter="(objectClass=inetOrgPerson)",
        group_search_base="ou=groups,dc=bbz,dc=test",
        start_tls=True,
        tls_verify=False,
    )
    report = await DirectorySyncService(s, client=LdapClient(cfg)).run()
    assert report.ok and report.scanned == 2 and report.created == 2
    await s.rollback()
    subjects = set(
        (
            await s.execute(select(AuthIdentity.subject).where(AuthIdentity.provider == "ldap_ad"))
        ).scalars()
    )
    assert subjects == {"disp1", "sicht1"}


@_REAL
async def test_real_sync_reconciles_group_roles_from_the_directory(s: AsyncSession) -> None:
    from bbz_core.auth.ldap import LdapClient, LdapConfig

    await _role(s, "sichtleiter")
    await s.rollback()
    async with s.begin():
        s.add(
            AuthGroupMapping(
                provider="ldap_ad",
                external_group="leitstelle-sichtleiter",
                role_key="sichtleiter",
            )
        )

    cfg = LdapConfig(
        urls=(f"ldap://{_LDAP_HOST}:389",),
        bind_dn="cn=admin,dc=bbz,dc=test",
        bind_password="adminpass",
        user_search_base="ou=people,dc=bbz,dc=test",
        group_search_base="ou=groups,dc=bbz,dc=test",
        start_tls=True,
        tls_verify=False,
    )
    await DirectorySyncService(s, client=LdapClient(cfg)).run()
    await s.rollback()
    ident = (
        await s.execute(select(AuthIdentity).where(AuthIdentity.subject == "sicht1"))
    ).scalar_one()
    assert await _user_role_keys(s, ident.user_id) == {"sichtleiter"}


# --- admin API --------------------------------------------------------


async def _admin(s: AsyncSession, perms: list[str]) -> None:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import LocalCredential

    async with s.begin():
        u = User(display_name="Admin")
        s.add(u)
        await s.flush()
        ident = AuthIdentity(user_id=u.id, provider="local", subject="admin")
        s.add(ident)
        await s.flush()
        s.add(
            LocalCredential(
                auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x")
            )
        )
        role = Role(key="r-admin", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _login_admin(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


async def test_dry_run_endpoint_returns_the_report(env: tuple) -> None:
    client, s = env
    await _dir_user(s, "ghost")
    await _admin(s, ["users.manage"])
    await _login_admin(client)

    # the endpoint uses the configured (unreachable) directory → a real run would
    # fail; a dry run still calls it, so patch the enumerator via the service.
    from bbz_core.infra.repositories import directory_sync as ds_mod

    class _Fake:
        def enumerate_principals(self):
            return [_p("keep")]

    orig = ds_mod.LdapClient
    ds_mod.LdapClient = lambda *_a, **_k: _Fake()  # type: ignore[assignment,misc]
    try:
        r = await client.post("/api/v1/auth/directory-sync", json={"dry_run": True})
    finally:
        ds_mod.LdapClient = orig  # type: ignore[assignment]

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] and body["deactivated_uids"] == ["ghost"]


async def test_sync_endpoint_needs_users_manage(env: tuple) -> None:
    client, s = env
    await _admin(s, ["users.view"])
    await _login_admin(client)
    r = await client.post("/api/v1/auth/directory-sync", json={})
    assert r.status_code == 403


async def test_state_endpoint_reports_the_last_run(env: tuple) -> None:
    client, s = env
    await _admin(s, ["users.manage"])
    await _login_admin(client)
    r = await client.get("/api/v1/auth/directory-sync/state")
    assert r.status_code == 200
    assert r.json()["last_run_at"] is None  # never run
