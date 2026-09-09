"""Per-operator WebRTC SIP endpoint config service (E13-11, ADR-0035): the SIP
password is stored ENCRYPTED, never returned by a view, never in an audit row;
the generated PJSIP carries the cleartext password (Asterisk needs it) but is
only ever streamed. Credentials are handed to the operator's own session."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.identity import User
from bbz_core.infra.models.sip_gateway import SipWebrtcEndpoint
from bbz_core.infra.repositories.sip_webrtc_config import (
    SipWebrtcConfigService,
    SipWebrtcNotConfigured,
    SipWebrtcNotFoundError,
)


@pytest.fixture(autouse=True)
def _sip_env() -> Iterator[None]:
    import bbz_core.settings as settings_mod

    os.environ["BBZ_SIP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    os.environ["BBZ_SIP_WEBRTC_WS_URL"] = "wss://sip.bbz.example:8089/ws"
    os.environ["BBZ_SIP_WEBRTC_ICE_SERVERS"] = "stun:stun.bbz.example:3478"
    settings_mod.get_settings.cache_clear()
    yield
    for k in ("BBZ_SIP_ENCRYPTION_KEY", "BBZ_SIP_WEBRTC_WS_URL", "BBZ_SIP_WEBRTC_ICE_SERVERS"):
        os.environ.pop(k, None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def svc(db: AsyncSession) -> AsyncIterator[SipWebrtcConfigService]:
    yield SipWebrtcConfigService(db)


async def _user(db: AsyncSession, name: str) -> uuid.UUID:
    u = User(display_name=name)
    db.add(u)
    await db.commit()
    return u.id


async def test_set_endpoint_mints_a_user_and_password_and_hides_the_secret(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Operator Eins")
    view = await svc.set_endpoint(uid, enabled=True, rotate_password=False, actor_id=uid)

    assert view.user_id == uid and view.enabled is True
    assert view.auth_username.startswith("op-")
    assert view.auth_password_configured is True
    assert not hasattr(view, "auth_password")

    row = (await db.execute(select(SipWebrtcEndpoint))).scalar_one()
    assert row.auth_password_ciphertext not in ("",)
    # the ciphertext is opaque — decrypting round-trips
    from bbz_core.infra.sip_secrets import decrypt_webrtc_password

    assert len(decrypt_webrtc_password(row.auth_password_ciphertext)) >= 20


async def test_update_keeps_the_password_unless_rotated(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Op")
    await svc.set_endpoint(uid, enabled=True, rotate_password=False, actor_id=uid)
    first = (await db.execute(select(SipWebrtcEndpoint))).scalar_one().auth_password_ciphertext

    await svc.set_endpoint(uid, enabled=False, rotate_password=False, actor_id=uid)
    same = (await db.execute(select(SipWebrtcEndpoint))).scalar_one()
    assert same.enabled is False
    assert same.auth_password_ciphertext == first  # untouched
    assert same.auth_username  # unchanged

    await svc.set_endpoint(uid, enabled=True, rotate_password=True, actor_id=uid)
    rotated = (await db.execute(select(SipWebrtcEndpoint))).scalar_one()
    assert rotated.auth_password_ciphertext != first


async def test_the_password_never_reaches_an_audit_row(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Op")
    await svc.set_endpoint(uid, enabled=True, rotate_password=False, actor_id=uid)
    creds = await svc.credentials_for(uid)
    assert creds is not None

    rows = (await db.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_WEBRTC_ENDPOINT_CONFIGURED" for r in rows)
    blob = " ".join(str(r.before) + str(r.after) for r in rows)
    assert creds.auth_password not in blob


async def test_credentials_for_returns_the_jssip_shape(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Op")
    await svc.set_endpoint(uid, enabled=True, rotate_password=False, actor_id=uid)

    creds = await svc.credentials_for(uid)
    assert creds is not None
    assert creds.ws_url == "wss://sip.bbz.example:8089/ws"
    assert creds.sip_uri == f"sip:{creds.auth_user}@sip.bbz.example"
    assert creds.auth_user.startswith("op-")
    assert creds.auth_password  # cleartext, for the browser
    assert creds.ice_servers == [{"urls": "stun:stun.bbz.example:3478"}]


async def test_credentials_for_is_none_without_an_enabled_endpoint(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Op")
    assert await svc.credentials_for(uid) is None  # no endpoint at all

    await svc.set_endpoint(uid, enabled=False, rotate_password=False, actor_id=uid)
    assert await svc.credentials_for(uid) is None  # disabled


async def test_credentials_for_raises_without_a_ws_url(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    import bbz_core.settings as settings_mod

    uid = await _user(db, "Op")
    await svc.set_endpoint(uid, enabled=True, rotate_password=False, actor_id=uid)

    os.environ.pop("BBZ_SIP_WEBRTC_WS_URL", None)
    settings_mod.get_settings.cache_clear()
    with pytest.raises(SipWebrtcNotConfigured):
        await svc.credentials_for(uid)


async def test_delete_endpoint_audits_and_404s_when_missing(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Op")
    with pytest.raises(SipWebrtcNotFoundError):
        await svc.delete_endpoint(uid, actor_id=uid)

    await svc.set_endpoint(uid, enabled=True, rotate_password=False, actor_id=uid)
    await svc.delete_endpoint(uid, actor_id=uid)
    assert (await db.execute(select(SipWebrtcEndpoint))).scalars().all() == []
    rows = (await db.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_WEBRTC_ENDPOINT_REMOVED" for r in rows)


async def test_render_pjsip_shapes_the_transport_and_endpoint(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Op")
    view = await svc.set_endpoint(uid, enabled=True, rotate_password=False, actor_id=uid)
    u = view.auth_username

    pjsip = await svc.render_pjsip()
    assert "[transport-wss]" in pjsip and "protocol = wss" in pjsip
    assert f"[{u}]\ntype = endpoint" in pjsip
    assert "webrtc = yes" in pjsip
    # a WebRTC client's Contact is a `*.invalid` URI + BBZ always bridges —
    # without these the softphone registers but never rings
    assert "rewrite_contact = yes" in pjsip
    assert "direct_media = no" in pjsip
    # endpoint / auth / aor all share the name `<u>` — the AOR MUST match the
    # REGISTER To-URI user (a `-aor` suffix breaks registration)
    assert f"[{u}]\ntype = auth" in pjsip
    assert f"[{u}]\ntype = aor" in pjsip
    assert f"aors = {u}\n" in pjsip and f"auth = {u}\n" in pjsip
    assert "max_contacts = 1" in pjsip and "remove_existing = yes" in pjsip

    creds = await svc.credentials_for(uid)
    assert creds is not None
    assert f"password = {creds.auth_password}" in pjsip  # Asterisk type=auth needs cleartext


async def test_render_pjsip_is_empty_without_enabled_endpoints(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    uid = await _user(db, "Op")
    await svc.set_endpoint(uid, enabled=False, rotate_password=False, actor_id=uid)
    assert await svc.render_pjsip() == ""


async def test_operator_endpoint_map_only_lists_enabled(
    svc: SipWebrtcConfigService, db: AsyncSession
) -> None:
    a = await _user(db, "A")
    b = await _user(db, "B")
    va = await svc.set_endpoint(a, enabled=True, rotate_password=False, actor_id=a)
    await svc.set_endpoint(b, enabled=False, rotate_password=False, actor_id=b)

    m = await svc.operator_endpoint_map()
    assert m == {str(a): va.auth_username}
