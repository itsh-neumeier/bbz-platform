"""Admin directory (LDAP) connection test (#723).

Unit-level: the endpoint's shape, the store→env config overlay, the
not-configured and permission paths. The real bind against ``bbz-e14-ldap`` is
`test_ldap_login.py::test_probe_*` (skipped without the container).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_MANAGE = ["system.settings.manage"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "admin-dir-test-secret-at-least-32-bytes-ok"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_user(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    if perms:
        role = Role(key=f"r-{username}", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            pid = (
                await s.execute(select(Permission.id).where(Permission.key == key))
            ).scalar_one_or_none()
            if pid is None:
                p = Permission(key=key, area=key.split(".")[0])
                s.add(p)
                await s.flush()
                pid = p.id
            s.add(RolePermission(role_id=role.id, permission_id=pid, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def test_test_endpoint_reports_not_configured_without_ldap(env: tuple, monkeypatch) -> None:
    from bbz_core.settings import get_settings

    for k in ("BBZ_LDAP_URL", "BBZ_LDAP_BIND_DN", "BBZ_LDAP_USER_SEARCH_BASE"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()

    client, s = env
    await _make_user(s, "dt1", _MANAGE)
    await _login(client, "dt1")

    r = await client.post("/api/v1/admin/directory/test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is False and body["bind_ok"] is False


async def test_test_endpoint_runs_a_probe_against_the_effective_config(
    env: tuple, monkeypatch
) -> None:
    from bbz_core.auth.ldap import LdapClient
    from bbz_core.settings import get_settings

    monkeypatch.setenv("BBZ_LDAP_URL", "ldaps://dir.invalid:636")
    monkeypatch.setenv("BBZ_LDAP_BIND_DN", "cn=svc,dc=bbz,dc=test")
    monkeypatch.setenv("BBZ_LDAP_BIND_PASSWORD", "secret")
    monkeypatch.setenv("BBZ_LDAP_USER_SEARCH_BASE", "ou=people,dc=bbz,dc=test")
    get_settings.cache_clear()

    seen: dict[str, object] = {}

    def _fake_probe(self: LdapClient) -> dict[str, object]:
        seen["urls"] = self._cfg.urls
        return {
            "reachable": True,
            "tls_ok": True,
            "bind_ok": True,
            "sample_count": 3,
            "error": None,
        }

    monkeypatch.setattr(LdapClient, "probe", _fake_probe)

    client, s = env
    await _make_user(s, "dt2", _MANAGE)
    await _login(client, "dt2")

    # a DB override for the URL must win over the env value
    await client.put(
        "/api/v1/admin/settings/directory",
        json={"values": {"directory.ldap_url": "ldaps://real.example:636"}},
    )
    r = await client.post("/api/v1/admin/directory/test")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "configured": True,
        "reachable": True,
        "tls_ok": True,
        "bind_ok": True,
        "sample_count": 3,
        "error": None,
    }
    assert seen["urls"] == ("ldaps://real.example:636",)


async def test_test_endpoint_needs_settings_manage(env: tuple) -> None:
    client, s = env
    await _make_user(s, "dt3", ["users.view"])
    await _login(client, "dt3")
    assert (await client.post("/api/v1/admin/directory/test")).status_code == 403
