"""WebRTC operator softphone API (E13-11, ADR-0035):

- admin CRUD under ``/admin/telephony/sip/webrtc`` needs ``integrations.configure``
  and never returns / audits the SIP password;
- ``GET /telephony/webrtc-credentials`` is session-gated, needs
  ``calls.answer`` / ``calls.dial``, and discloses the password to the
  operator's own session only;
- the generated ``asterisk-config`` PJSIP now also carries the WebRTC endpoints.
"""

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


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    import bbz_core.settings as settings_mod
    from bbz_core.auth import hashing
    from bbz_core.integrations_host import providers

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "sip-webrtc-test-secret-at-least-32-bytes!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_SIP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    os.environ["BBZ_SIP_WEBRTC_WS_URL"] = "wss://sip.bbz.example:8089/ws"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    providers.reset_provider_cache()
    settings_mod.get_settings.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    providers.reset_provider_cache()
    for k in ("BBZ_SIP_ENCRYPTION_KEY", "BBZ_SIP_WEBRTC_WS_URL"):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()


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


async def test_admin_routes_need_integrations_configure(env: tuple) -> None:
    client, s = env
    assert (await client.get("/api/v1/admin/telephony/sip/webrtc")).status_code == 401
    await _make_user(s, "nobody", [])
    await _login(client, "nobody")
    assert (await client.get("/api/v1/admin/telephony/sip/webrtc")).status_code == 403


async def test_admin_put_creates_an_endpoint_without_returning_the_password(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    op = await _make_user(s, "op", [])
    await _login(client, "cfg")

    r = await client.put(f"/api/v1/admin/telephony/sip/webrtc/{op}", json={"enabled": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == str(op)
    assert body["auth_username"].startswith("op-")
    assert body["auth_password_configured"] is True
    assert "auth_password" not in body

    listed = (await client.get("/api/v1/admin/telephony/sip/webrtc")).json()
    assert [e["user_id"] for e in listed["endpoints"]] == [str(op)]


async def test_admin_put_for_an_unknown_user_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    r = await client.put(
        f"/api/v1/admin/telephony/sip/webrtc/{uuid.uuid4()}", json={"enabled": True}
    )
    assert r.status_code == 404


async def test_admin_password_never_in_an_audit_row(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    op = await _make_user(s, "op", ["calls.answer"])
    await _login(client, "cfg")
    await client.put(f"/api/v1/admin/telephony/sip/webrtc/{op}", json={"enabled": True})

    # fetch the operator's cleartext password (a separate session below), then
    # assert it is nowhere in the audit trail
    await _login(client, "op")
    creds = (await client.get("/api/v1/telephony/webrtc-credentials")).json()

    rows = (await s.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_WEBRTC_ENDPOINT_CONFIGURED" for r in rows)
    blob = " ".join(str(r.before) + str(r.after) for r in rows)
    assert creds["auth_password"] not in blob


async def test_credentials_endpoint_is_session_scoped_and_permission_gated(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    op = await _make_user(s, "op", ["calls.answer"])
    noperm = await _make_user(s, "guest", [])
    await _login(client, "cfg")
    await client.put(f"/api/v1/admin/telephony/sip/webrtc/{op}", json={"enabled": True})
    await client.put(f"/api/v1/admin/telephony/sip/webrtc/{noperm}", json={"enabled": True})

    # the operator gets their own creds
    await _login(client, "op")
    r = await client.get("/api/v1/telephony/webrtc-credentials")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["auth_user"].startswith("op-")
    assert body["ws_url"] == "wss://sip.bbz.example:8089/ws"
    assert body["sip_uri"].endswith("@sip.bbz.example")
    assert body["auth_password"]

    # a user without calls.answer / calls.dial cannot, even with an endpoint row
    await _login(client, "guest")
    assert (await client.get("/api/v1/telephony/webrtc-credentials")).status_code == 403


async def test_credentials_endpoint_404s_without_an_endpoint(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["calls.dial"])
    await _login(client, "op")
    assert (await client.get("/api/v1/telephony/webrtc-credentials")).status_code == 404


async def test_disabling_the_endpoint_makes_credentials_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    op = await _make_user(s, "op", ["calls.answer"])
    await _login(client, "cfg")
    await client.put(f"/api/v1/admin/telephony/sip/webrtc/{op}", json={"enabled": True})
    await client.put(f"/api/v1/admin/telephony/sip/webrtc/{op}", json={"enabled": False})

    await _login(client, "op")
    assert (await client.get("/api/v1/telephony/webrtc-credentials")).status_code == 404


async def test_delete_endpoint_removes_it(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    op = await _make_user(s, "op", [])
    await _login(client, "cfg")
    await client.put(f"/api/v1/admin/telephony/sip/webrtc/{op}", json={"enabled": True})

    assert (await client.delete(f"/api/v1/admin/telephony/sip/webrtc/{op}")).status_code == 204
    assert (await client.get("/api/v1/admin/telephony/sip/webrtc")).json()["endpoints"] == []
    r = await client.delete(f"/api/v1/admin/telephony/sip/webrtc/{op}")
    assert r.status_code == 404


async def test_asterisk_config_pjsip_carries_the_webrtc_endpoints(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    op = await _make_user(s, "op", ["calls.answer"])
    await _login(client, "cfg")
    put = await client.put(f"/api/v1/admin/telephony/sip/webrtc/{op}", json={"enabled": True})
    user = put.json()["auth_username"]

    r = await client.get("/api/v1/admin/telephony/sip/asterisk-config?part=pjsip")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert "[transport-wss]" in r.text
    assert f"[{user}]" in r.text and "webrtc = yes" in r.text
