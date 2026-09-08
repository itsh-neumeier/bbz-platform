"""SIP trunk (ITSP) config service + Asterisk config generation (E13-09,
ADR-0034): trunk auth passwords are stored ENCRYPTED, never returned by a view,
never in an audit row; the generated config carries the cleartext password
(PJSIP needs it) but is only ever streamed, never persisted by BBZ."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.sip_gateway import SipNumber, SipTrunk
from bbz_core.infra.repositories.sip_trunk_config import (
    SipTrunkConfigService,
    SipTrunkError,
    SipTrunkNotFoundError,
)

_PW = "leonet-trunk-pw-9931"
_NUM_PW = "msn-pw-4471"


@pytest.fixture(autouse=True)
def _sip_key() -> Iterator[None]:
    import bbz_core.settings as settings_mod

    os.environ["BBZ_SIP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    settings_mod.get_settings.cache_clear()
    yield
    os.environ.pop("BBZ_SIP_ENCRYPTION_KEY", None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def svc(db: AsyncSession) -> AsyncIterator[SipTrunkConfigService]:
    yield SipTrunkConfigService(db)


def _trunk(**over: object) -> dict[str, object]:
    return {
        "provider": "leonet",
        "display_name": "LEONET",
        "enabled": True,
        "sip_server": "sip.leovoice.online",
        "sip_port": 5060,
        "transport": "udp",
        "outbound_proxy": "",
        "from_domain": "sip.leovoice.online",
        "registration": True,
        "auth_username": "leo4991150099",
        "auth_password": _PW,
        "match_hosts": "91.106.121.3/32",
        "codecs": "alaw,ulaw",
        "dtmf_mode": "rfc4733",
        "caller_id_e164": "+4991150099",
        "actor_id": None,
        **over,
    }


async def test_set_trunk_encrypts_the_password_and_the_view_hides_it(
    svc: SipTrunkConfigService, db: AsyncSession
) -> None:
    view = await svc.set_trunk("leonet", **_trunk())  # type: ignore[arg-type]
    assert view.trunk_id == "leonet" and view.enabled is True
    assert view.auth_password_configured is True
    assert not hasattr(view, "auth_password")

    row = (await db.execute(select(SipTrunk))).scalar_one()
    assert row.auth_password_ciphertext not in ("", _PW)
    assert _PW not in row.auth_password_ciphertext


async def test_set_trunk_without_a_password_keeps_the_stored_one(
    svc: SipTrunkConfigService,
) -> None:
    await svc.set_trunk("leonet", **_trunk())  # type: ignore[arg-type]
    updated = await svc.set_trunk(
        "leonet",
        **_trunk(auth_password=None, display_name="LEONET Süd"),  # type: ignore[arg-type]
    )
    assert updated.display_name == "LEONET Süd"
    assert updated.auth_password_configured is True


async def test_the_trunk_password_never_reaches_an_audit_row(
    svc: SipTrunkConfigService, db: AsyncSession
) -> None:
    await svc.set_trunk("leonet", **_trunk())  # type: ignore[arg-type]
    rows = (await db.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_TRUNK_CONFIGURED" for r in rows)
    blob = " ".join(str(r.before) + str(r.after) for r in rows)
    assert _PW not in blob


async def test_slug_and_enum_validation(svc: SipTrunkConfigService) -> None:
    with pytest.raises(SipTrunkError):
        await svc.set_trunk("Not A Slug", **_trunk())  # type: ignore[arg-type]
    with pytest.raises(SipTrunkError):
        await svc.set_trunk("t1", **_trunk(transport="sctp"))  # type: ignore[arg-type]
    with pytest.raises(SipTrunkError):
        await svc.set_trunk("t1", **_trunk(enabled=True, sip_server=""))  # type: ignore[arg-type]
    with pytest.raises(SipTrunkError):
        await svc.set_trunk("t1", **_trunk(match_hosts="not-an-ip/33"))  # type: ignore[arg-type]


async def test_register_requires_an_auth_username(svc: SipTrunkConfigService) -> None:
    with pytest.raises(SipTrunkError):
        await svc.set_trunk(
            "t1",
            **_trunk(registration=True, auth_username="", auth_password=None),  # type: ignore[arg-type]
        )


async def test_number_crud_needs_an_existing_trunk_and_e164(
    svc: SipTrunkConfigService,
) -> None:
    with pytest.raises(SipTrunkNotFoundError):
        await svc.set_number(
            "+4991150099",
            trunk_id="leonet",
            bbz_line_id="tor-1",
            label="Tor 1",
            registration=False,
            auth_username="",
            auth_password=None,
            enabled=True,
            actor_id=None,
        )
    await svc.set_trunk("leonet", **_trunk())  # type: ignore[arg-type]
    with pytest.raises(SipTrunkError):
        await svc.set_number(
            "089-nope",
            trunk_id="leonet",
            bbz_line_id="",
            label="",
            registration=False,
            auth_username="",
            auth_password=None,
            enabled=True,
            actor_id=None,
        )
    n = await svc.set_number(
        "+4991150099",
        trunk_id="leonet",
        bbz_line_id="tor-1",
        label="Tor 1",
        registration=True,
        auth_username="leo4991150099",
        auth_password=_NUM_PW,
        enabled=True,
        actor_id=None,
    )
    assert n.e164 == "+4991150099" and n.auth_password_configured is True
    assert [v.e164 for v in await svc.list_numbers(trunk_id="leonet")] == ["+4991150099"]


async def test_deleting_a_trunk_cascades_its_numbers(
    svc: SipTrunkConfigService, db: AsyncSession
) -> None:
    await svc.set_trunk("leonet", **_trunk())  # type: ignore[arg-type]
    await svc.set_number(
        "+4991150099",
        trunk_id="leonet",
        bbz_line_id="tor-1",
        label="",
        registration=False,
        auth_username="",
        auth_password=None,
        enabled=True,
        actor_id=None,
    )
    await svc.delete_trunk("leonet", actor_id=None)
    assert (await db.execute(select(SipNumber))).scalars().all() == []
    rows = (await db.execute(select(AuditEvent))).scalars().all()
    assert any(r.action == "SIP_TRUNK_REMOVED" for r in rows)


async def test_render_asterisk_config_shapes_the_pjsip_and_dialplan(
    svc: SipTrunkConfigService,
) -> None:
    await svc.set_trunk("leonet", **_trunk())  # type: ignore[arg-type]
    await svc.set_number(
        "+4991150099",
        trunk_id="leonet",
        bbz_line_id="tor-1",
        label="Tor 1",
        registration=True,
        auth_username="leo4991150099",
        auth_password=_NUM_PW,
        enabled=True,
        actor_id=None,
    )
    rendered = await svc.render_asterisk_config()

    # PJSIP: the trunk sections + the decrypted password + per-MSN registration
    assert "[leonet]" in rendered.pjsip
    assert "type = registration" in rendered.pjsip
    assert "[leonet-identify]" in rendered.pjsip
    assert "match = 91.106.121.3/32" in rendered.pjsip
    assert f"password = {_PW}" in rendered.pjsip
    assert "[leonet-n-4991150099-reg]" in rendered.pjsip
    assert f"password = {_NUM_PW}" in rendered.pjsip

    # dialplan: inbound context -> Stasis(bbz-sip, <line>)
    assert "[from-leonet]" in rendered.extensions
    assert "Stasis(bbz-sip,${BBZ_LINE})" in rendered.extensions
    assert "Set(BBZ_LINE=tor-1)" in rendered.extensions


async def test_render_skips_disabled_trunks(svc: SipTrunkConfigService) -> None:
    await svc.set_trunk("leonet", **_trunk(enabled=False))  # type: ignore[arg-type]
    rendered = await svc.render_asterisk_config()
    assert "[leonet]" not in rendered.pjsip
    assert "BBZ — generated SIP trunk config" in rendered.pjsip  # header still there


async def test_render_leonet_per_msn_no_trunk_level_auth(svc: SipTrunkConfigService) -> None:
    """LEONET: the trunk itself does not register (no trunk auth); each public
    number carries its own SIP user/password and registers separately."""
    await svc.set_trunk(
        "leonet",
        **_trunk(registration=False, auth_username="", auth_password=None),  # type: ignore[arg-type]
    )
    await svc.set_number(
        "+4995434448870",
        trunk_id="leonet",
        bbz_line_id="leonet-8870",
        label="MSN 8870",
        registration=True,
        auth_username="4448870",
        auth_password="msn-secret",
        enabled=True,
        actor_id=None,
    )
    pjsip = (await svc.render_asterisk_config()).pjsip
    # no trunk-level auth/registration section
    assert "[leonet-auth]" not in pjsip
    assert "[leonet-reg]" not in pjsip
    # inbound identify + a lean endpoint + the per-MSN registration
    assert "[leonet-identify]" in pjsip and "match = 91.106.121.3/32" in pjsip
    assert "[leonet]\ntype = endpoint" in pjsip
    assert "outbound_auth = leonet-auth" not in pjsip
    assert "[leonet-n-4995434448870-auth]" in pjsip
    assert "[leonet-n-4995434448870-reg]" in pjsip
    assert "outbound_auth = leonet-n-4995434448870-auth" in pjsip
    assert "password = msn-secret" in pjsip


async def test_outbound_line_map_routes_a_numbered_line_through_its_trunk(
    svc: SipTrunkConfigService,
) -> None:
    """E13-10: a public number with a bbz_line_id -> an outbound dial template
    `PJSIP/{dest}@<trunk>` + the trunk caller-id (or the number itself)."""
    await svc.set_trunk("leonet", **_trunk(caller_id_e164=""))  # type: ignore[arg-type]
    await svc.set_number(
        "+4991150099",
        trunk_id="leonet",
        bbz_line_id="tor-1",
        label="Tor 1",
        registration=True,
        auth_username="leo4991150099",
        auth_password="pw",
        enabled=True,
        actor_id=None,
    )
    # a number without a line, and a disabled one, don't appear
    await svc.set_number(
        "+4991150098",
        trunk_id="leonet",
        bbz_line_id="",
        label="",
        registration=False,
        auth_username="",
        auth_password=None,
        enabled=True,
        actor_id=None,
    )
    m = await svc.outbound_line_map()
    assert m == {"tor-1": {"endpoint": "PJSIP/{dest}@leonet", "caller_id": "+4991150099"}}

    # trunk caller_id_e164 wins when set
    await svc.set_trunk("leonet", **_trunk(caller_id_e164="+4991150000"))  # type: ignore[arg-type]
    assert (await svc.outbound_line_map())["tor-1"]["caller_id"] == "+4991150000"

    # a disabled trunk drops its lines
    await svc.set_trunk("leonet", **_trunk(enabled=False))  # type: ignore[arg-type]
    assert await svc.outbound_line_map() == {}
