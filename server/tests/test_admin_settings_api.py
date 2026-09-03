"""Runtime settings store — the admin API (ADR-0031 / #720).

Covers: DB override beats env, env is the fallback, every write is one
``SETTING_CHANGED`` row, secrets are never persisted or returned, validation,
idempotency, and the ``system.settings.manage`` gate.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.app_settings import AppSetting
from bbz_core.infra.models.audit import AuditEvent

_MANAGE = ["system.settings.manage"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "settings-test-secret-at-least-32-bytes-ok!"
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


async def _audit_count(s: AsyncSession, action: str) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


def _item(groups: list[dict], key: str) -> dict:
    for g in groups:
        for i in g["items"]:
            if i["key"] == key:
                return i
    raise AssertionError(f"{key} not in response")


async def test_get_lists_groups_with_effective_values_and_source(env: tuple) -> None:
    client, s = env
    await _make_user(s, "st1", _MANAGE)
    await _login(client, "st1")

    r = await client.get("/api/v1/admin/settings")
    assert r.status_code == 200, r.text
    groups = r.json()["groups"]
    assert [g["group"] for g in groups] == ["instance", "directory", "integrations"]

    name = _item(groups, "instance.name")
    assert name["value"] == "BBZ / 3-S-Zentrale"
    assert name["source"] == "default" and name["overridden"] is False


async def test_a_db_override_beats_env_and_is_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "st2", _MANAGE)
    await _login(client, "st2")

    r = await client.put(
        "/api/v1/admin/settings/instance", json={"values": {"instance.name": "BBZ Nürnberg"}}
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == ["instance.name"]
    assert _item(r.json()["groups"], "instance.name")["value"] == "BBZ Nürnberg"

    got = _item((await client.get("/api/v1/admin/settings")).json()["groups"], "instance.name")
    assert got["value"] == "BBZ Nürnberg"
    assert got["source"] == "database" and got["overridden"] is True

    await s.rollback()
    row = await s.get(AppSetting, "instance.name")
    assert row is not None and row.value == "BBZ Nürnberg"
    assert await _audit_count(s, "SETTING_CHANGED") == 1
    ev = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "SETTING_CHANGED"))
    ).scalar_one()
    assert ev.target_id == "instance"
    assert ev.after == {"instance.name": "BBZ Nürnberg"}
    assert ev.before == {"instance.name": "BBZ / 3-S-Zentrale"}


async def test_env_is_the_fallback_until_a_value_is_set(env: tuple, monkeypatch) -> None:
    from bbz_core.settings import get_settings

    monkeypatch.setenv("BBZ_MONITOR_INTEGRATION_ID", "monitor_weytec")
    get_settings.cache_clear()

    client, s = env
    await _make_user(s, "st3", _MANAGE)
    await _login(client, "st3")

    got = _item(
        (await client.get("/api/v1/admin/settings")).json()["groups"], "integrations.monitor"
    )
    assert got["value"] == "monitor_weytec" and got["source"] == "environment"

    r = await client.put(
        "/api/v1/admin/settings/integrations",
        json={"values": {"integrations.monitor": "monitor_mock"}},
    )
    assert r.status_code == 200
    got = _item(r.json()["groups"], "integrations.monitor")
    assert got["value"] == "monitor_mock" and got["source"] == "database"


async def test_put_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "st4", _MANAGE)
    await _login(client, "st4")

    body = {"values": {"instance.short_name": "3SZ"}}
    assert (await client.put("/api/v1/admin/settings/instance", json=body)).json()["updated"] == [
        "instance.short_name"
    ]
    r2 = await client.put("/api/v1/admin/settings/instance", json=body)
    assert r2.status_code == 200 and r2.json()["updated"] == []

    await s.rollback()
    assert await _audit_count(s, "SETTING_CHANGED") == 1


async def test_put_rejects_unknown_key_and_foreign_group(env: tuple) -> None:
    client, s = env
    await _make_user(s, "st5", _MANAGE)
    await _login(client, "st5")

    r = await client.put("/api/v1/admin/settings/instance", json={"values": {"instance.nope": "x"}})
    assert r.status_code == 422 and "unknown setting" in r.text

    # a real key, wrong group
    r = await client.put(
        "/api/v1/admin/settings/instance", json={"values": {"integrations.monitor": "x"}}
    )
    assert r.status_code == 422

    r = await client.put("/api/v1/admin/settings/bogus", json={"values": {"a.b": "c"}})
    assert r.status_code == 422


async def test_a_required_string_may_not_be_blanked(env: tuple) -> None:
    client, s = env
    await _make_user(s, "st6", _MANAGE)
    await _login(client, "st6")
    r = await client.put(
        "/api/v1/admin/settings/instance", json={"values": {"instance.name": "   "}}
    )
    assert r.status_code == 422 and "must not be empty" in r.text


async def test_secret_keys_are_read_only_and_never_leak(env: tuple, monkeypatch) -> None:
    from bbz_core.settings import get_settings

    client, s = env
    await _make_user(s, "st7", _MANAGE)
    await _login(client, "st7")

    got = _item(
        (await client.get("/api/v1/admin/settings")).json()["groups"],
        "directory.ldap_bind_password",
    )
    assert got["secret"] is True and got["value"] is None and got["configured"] is False

    # cannot be written through this API
    r = await client.put(
        "/api/v1/admin/settings/directory",
        json={"values": {"directory.ldap_bind_password": "hunter2"}},
    )
    assert r.status_code == 422 and "secret" in r.text.lower()
    await s.rollback()
    assert (await s.execute(select(func.count()).select_from(AppSetting))).scalar_one() == 0

    # a value from the environment shows only as "configured", never in the clear
    monkeypatch.setenv("BBZ_LDAP_BIND_PASSWORD", "hunter2")
    get_settings.cache_clear()
    got = _item(
        (await client.get("/api/v1/admin/settings")).json()["groups"],
        "directory.ldap_bind_password",
    )
    assert got["configured"] is True and got["value"] is None
    assert "hunter2" not in (await client.get("/api/v1/admin/settings")).text


async def test_meta_reflects_the_instance_name_override(env: tuple) -> None:
    client, s = env
    await _make_user(s, "st9", _MANAGE)
    await _login(client, "st9")

    assert (await client.get("/api/v1/meta")).json()["instance_name"] == "BBZ / 3-S-Zentrale"

    await client.put(
        "/api/v1/admin/settings/instance",
        json={"values": {"instance.name": "BBZ Nürnberg", "instance.short_name": "NBG"}},
    )
    meta = (await client.get("/api/v1/meta")).json()
    assert meta["instance_name"] == "BBZ Nürnberg"
    assert meta["instance_short_name"] == "NBG"


async def test_requires_the_manage_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "st8", ["system.audit.view"])
    await _login(client, "st8")

    assert (await client.get("/api/v1/admin/settings")).status_code == 403
    r = await client.put("/api/v1/admin/settings/instance", json={"values": {"instance.name": "X"}})
    assert r.status_code == 403
