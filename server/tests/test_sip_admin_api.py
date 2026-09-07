"""SIP gateway admin API (E13-07, ADR-0033): the ARI password enters write-only,
is never returned, and every route needs `integrations.configure`. Mirrors the
door-action-profile API guarantees."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent

_PW = "top-s3cret-ari"


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core.auth import hashing
    from bbz_core.integrations_host import providers

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "sip-admin-test-secret-at-least-32-bytes!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_SIP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    providers.reset_provider_cache()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    providers.reset_provider_cache()
    os.environ.pop("BBZ_SIP_ENCRYPTION_KEY", None)


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


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    assert isinstance(db, AsyncSession)
    yield client, db


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _body(**over: object) -> dict[str, object]:
    return {
        "host": "pbx.bbz.internal",
        "port": 8088,
        "tls": True,
        "app_name": "bbz-sip",
        "dtmf_transport": "rfc2833",
        "ari_username": "bbz",
        "ari_password": _PW,
        "enabled": True,
        **over,
    }


async def test_routes_need_integrations_configure(env: tuple) -> None:
    client, s = env
    assert (await client.get("/api/v1/admin/telephony/sip")).status_code == 401
    await _make_user(s, "nobody", [])
    await _login(client, "nobody")
    assert (await client.get("/api/v1/admin/telephony/sip")).status_code == 403


async def test_put_then_get_roundtrips_without_the_password(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")

    r = await client.put("/api/v1/admin/telephony/sip", json=_body())
    assert r.status_code == 200, r.text
    assert "ari_password" not in r.json()["gateway"]

    got = (await client.get("/api/v1/admin/telephony/sip")).json()
    assert got["gateway"]["host"] == "pbx.bbz.internal"
    assert got["gateway"]["ari_password_configured"] is True
    assert got["gateway"]["enabled"] is True
    assert got["active"] is False  # telephony_mock is the default provider


async def test_the_password_is_never_in_an_audit_row(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    await client.put("/api/v1/admin/telephony/sip", json=_body())

    rows = (await s.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_GATEWAY_CONFIGURED" for r in rows)
    assert _PW not in " ".join(str(r.before) + str(r.after) for r in rows)


async def test_enabling_without_a_host_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    r = await client.put("/api/v1/admin/telephony/sip", json=_body(host="", enabled=True))
    assert r.status_code == 422


async def test_a_missing_encryption_key_is_503(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    os.environ.pop("BBZ_SIP_ENCRYPTION_KEY", None)
    import bbz_core.settings as settings_mod

    settings_mod.get_settings.cache_clear()
    r = await client.put("/api/v1/admin/telephony/sip", json=_body())
    assert r.status_code == 503


async def test_line_crud(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")

    r = await client.put(
        "/api/v1/admin/telephony/sip/lines/1001",
        json={"asterisk_endpoint": None, "label": "Tor 1", "enabled": True},
    )
    assert r.status_code == 200 and r.json()["asterisk_endpoint"] == "PJSIP/1001"

    listed = (await client.get("/api/v1/admin/telephony/sip")).json()["lines"]
    assert [line["bbz_line_id"] for line in listed] == ["1001"]

    assert (await client.delete("/api/v1/admin/telephony/sip/lines/1001")).status_code == 204
    assert (await client.get("/api/v1/admin/telephony/sip")).json()["lines"] == []


async def test_test_connection_reports_unreachable_for_a_dead_gateway(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")

    r = await client.post(
        "/api/v1/admin/telephony/sip/test",
        json={
            "host": "127.0.0.1",
            "port": 1,
            "tls": False,
            "ari_username": "x",
            "ari_password": "y",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["reachable"] is False


async def test_test_connection_without_a_body_probes_the_stored_config(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    # a disabled gateway is still probeable
    await client.put(
        "/api/v1/admin/telephony/sip", json=_body(host="127.0.0.1", port=1, enabled=False)
    )

    r = await client.post("/api/v1/admin/telephony/sip/test")
    assert r.status_code == 200 and r.json()["reachable"] is False
