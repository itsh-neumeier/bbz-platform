"""SIP trunk (ITSP) admin API (E13-09, ADR-0034): trunk passwords enter
write-only and are never returned; the generated Asterisk config is ``no-store``
and every route needs ``integrations.configure``."""

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

_PW = "leonet-trunk-s3cret"


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core.auth import hashing
    from bbz_core.integrations_host import providers

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "sip-trunk-test-secret-at-least-32-bytes!!"
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


def _trunk(**over: object) -> dict[str, object]:
    return {
        "provider": "leonet",
        "display_name": "LEONET",
        "enabled": True,
        "sip_server": "sip.leovoice.online",
        "sip_port": 5060,
        "transport": "udp",
        "from_domain": "sip.leovoice.online",
        "registration": True,
        "auth_username": "leo4991150099",
        "auth_password": _PW,
        "match_hosts": "91.106.121.3/32",
        "codecs": "alaw,ulaw",
        "dtmf_mode": "rfc4733",
        "caller_id_e164": "+4991150099",
        **over,
    }


async def test_routes_need_integrations_configure(env: tuple) -> None:
    client, s = env
    assert (await client.get("/api/v1/admin/telephony/sip/trunks")).status_code == 401
    await _make_user(s, "nobody", [])
    await _login(client, "nobody")
    assert (await client.get("/api/v1/admin/telephony/sip/trunks")).status_code == 403


async def test_trunk_put_get_roundtrips_without_the_password(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")

    r = await client.put("/api/v1/admin/telephony/sip/trunks/leonet", json=_trunk())
    assert r.status_code == 200, r.text
    assert "auth_password" not in r.json()
    assert r.json()["auth_password_configured"] is True

    listed = (await client.get("/api/v1/admin/telephony/sip/trunks")).json()
    assert [t["trunk_id"] for t in listed["trunks"]] == ["leonet"]
    assert listed["trunks"][0]["sip_server"] == "sip.leovoice.online"


async def test_trunk_password_never_in_an_audit_row(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    await client.put("/api/v1/admin/telephony/sip/trunks/leonet", json=_trunk())

    rows = (await s.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_TRUNK_CONFIGURED" for r in rows)
    assert _PW not in " ".join(str(r.before) + str(r.after) for r in rows)


async def test_enabling_without_a_server_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    r = await client.put(
        "/api/v1/admin/telephony/sip/trunks/leonet", json=_trunk(sip_server="", enabled=True)
    )
    assert r.status_code == 422


async def test_number_crud_and_cascade(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    await client.put("/api/v1/admin/telephony/sip/trunks/leonet", json=_trunk())

    r = await client.put(
        "/api/v1/admin/telephony/sip/numbers/%2B4991150099",
        json={"trunk_id": "leonet", "bbz_line_id": "tor-1", "label": "Tor 1", "enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["e164"] == "+4991150099"

    listed = (await client.get("/api/v1/admin/telephony/sip/trunks")).json()
    assert [n["e164"] for n in listed["numbers"]] == ["+4991150099"]

    # deleting the trunk cascades the number
    assert (await client.delete("/api/v1/admin/telephony/sip/trunks/leonet")).status_code == 204
    assert (await client.get("/api/v1/admin/telephony/sip/trunks")).json()["numbers"] == []


async def test_number_on_a_missing_trunk_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    r = await client.put(
        "/api/v1/admin/telephony/sip/numbers/%2B4991150099",
        json={"trunk_id": "ghost", "bbz_line_id": "", "label": "", "enabled": True},
    )
    assert r.status_code == 404


async def test_asterisk_config_is_no_store_and_has_the_sections(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    await client.put("/api/v1/admin/telephony/sip/trunks/leonet", json=_trunk())
    await client.put(
        "/api/v1/admin/telephony/sip/numbers/%2B4991150099",
        json={"trunk_id": "leonet", "bbz_line_id": "tor-1", "label": "", "enabled": True},
    )

    r = await client.get("/api/v1/admin/telephony/sip/asterisk-config")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-type"].startswith("text/plain")
    assert "[leonet]" in r.text
    assert "[from-leonet]" in r.text
    assert "Stasis(bbz-sip,${BBZ_LINE})" in r.text
    assert _PW in r.text  # PJSIP type=auth needs the cleartext password

    pj = await client.get("/api/v1/admin/telephony/sip/asterisk-config?part=pjsip")
    assert "[from-leonet]" not in pj.text and "[leonet-auth]" in pj.text


async def test_trunk_test_probe_without_a_gateway(env: tuple) -> None:
    client, s = env
    await _make_user(s, "cfg", ["integrations.configure"])
    await _login(client, "cfg")
    await client.put("/api/v1/admin/telephony/sip/trunks/leonet", json=_trunk())

    r = await client.post("/api/v1/admin/telephony/sip/trunks/leonet/test")
    assert r.status_code == 200, r.text
    # no SIP gateway (Asterisk/ARI) configured in this test -> unreachable
    assert r.json()["state"] == "unreachable"

    assert (await client.post("/api/v1/admin/telephony/sip/trunks/ghost/test")).status_code == 404


def test_trunk_probe_state_maps_ari_endpoints() -> None:
    """`offline`/`unknown` from ARI -> `loaded` (a registering / inbound-only
    trunk is not "misconfigured"); only a reachable contact is `online`."""
    from bbz_core.integrations_host.providers import _trunk_probe_state

    assert _trunk_probe_state([], "leonet-01")[0] == "not_loaded"

    offline = [{"technology": "PJSIP", "resource": "leonet-01", "state": "offline"}]
    state, detail = _trunk_probe_state(offline, "leonet-01")
    assert state == "loaded"
    assert "pjsip show registrations" in detail

    online = [
        {"technology": "PJSIP", "resource": "leonet-01", "state": "online", "channel_ids": ["c1"]}
    ]
    assert _trunk_probe_state(online, "leonet-01") == (
        "online",
        "PJSIP/leonet-01 is online (1 active channel(s))",
    )

    # a different trunk's endpoint doesn't count
    assert _trunk_probe_state(online, "telekom")[0] == "not_loaded"
