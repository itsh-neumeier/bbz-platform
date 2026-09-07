"""SIP gateway config service (E13-07, ADR-0033): the ARI password is stored
ENCRYPTED, never returned, never in an audit row, never plaintext in the DB.
Mirrors the door-action-profile guarantees."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.sip_gateway import SipGateway
from bbz_core.infra.repositories.sip_config import SipConfigError, SipConfigService

_PASSWORD = "s3cret-ari-pw"


@pytest.fixture(autouse=True)
def _sip_key() -> Iterator[None]:
    import bbz_core.settings as settings_mod

    os.environ["BBZ_SIP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    settings_mod.get_settings.cache_clear()
    yield
    os.environ.pop("BBZ_SIP_ENCRYPTION_KEY", None)
    settings_mod.get_settings.cache_clear()


@pytest.fixture
async def svc(db: AsyncSession) -> AsyncIterator[SipConfigService]:
    yield SipConfigService(db)


def _base(**over: object) -> dict[str, object]:
    return {
        "host": "pbx.bbz.internal",
        "port": 8088,
        "tls": True,
        "app_name": "bbz-sip",
        "dtmf_transport": "rfc2833",
        "ari_username": "bbz",
        "ari_password": _PASSWORD,
        "enabled": True,
        "actor_id": None,
        **over,
    }


async def test_get_returns_a_safe_default_when_unconfigured(svc: SipConfigService) -> None:
    view = await svc.get()
    assert view.host == "" and view.enabled is False
    assert view.ari_password_configured is False


async def test_set_persists_and_encrypts_the_password(
    svc: SipConfigService, db: AsyncSession
) -> None:
    view = await svc.set(**_base())  # type: ignore[arg-type]
    assert view.host == "pbx.bbz.internal" and view.enabled is True
    assert view.ari_password_configured is True

    row = (await db.execute(select(SipGateway))).scalar_one()
    assert row.ari_password_ciphertext not in ("", _PASSWORD)  # stored encrypted
    assert _PASSWORD not in row.ari_password_ciphertext


async def test_set_without_a_password_keeps_the_stored_one(svc: SipConfigService) -> None:
    await svc.set(**_base())  # type: ignore[arg-type]
    updated = await svc.set(**_base(ari_password=None, ari_username="bbz2"))  # type: ignore[arg-type]
    assert updated.ari_username == "bbz2"
    assert updated.ari_password_configured is True  # unchanged


async def test_the_password_never_reaches_an_audit_row(
    svc: SipConfigService, db: AsyncSession
) -> None:
    await svc.set(**_base())  # type: ignore[arg-type]
    rows = (await db.execute(select(AuditEvent))).scalars().all()
    assert rows and any(r.action == "SIP_GATEWAY_CONFIGURED" for r in rows)
    blob = " ".join(str(r.before) + str(r.after) for r in rows)
    assert _PASSWORD not in blob


async def test_enabling_without_a_host_is_rejected(svc: SipConfigService) -> None:
    with pytest.raises(SipConfigError):
        await svc.set(**_base(host="", enabled=True))  # type: ignore[arg-type]


async def test_an_unknown_dtmf_transport_is_rejected(svc: SipConfigService) -> None:
    with pytest.raises(SipConfigError):
        await svc.set(**_base(dtmf_transport="q931"))  # type: ignore[arg-type]


async def test_line_crud_and_endpoint_default(svc: SipConfigService) -> None:
    a = await svc.set_line(
        "1001", asterisk_endpoint=None, label="Tor 1", enabled=True, actor_id=None
    )
    assert a.asterisk_endpoint == "PJSIP/1001"  # the default
    await svc.set_line(
        "1002", asterisk_endpoint="PJSIP/side-gate", label="", enabled=False, actor_id=None
    )
    lines = await svc.list_lines()
    assert {line.bbz_line_id for line in lines} == {"1001", "1002"}

    await svc.delete_line("1002", actor_id=None)
    assert [line.bbz_line_id for line in await svc.list_lines()] == ["1001"]


async def test_runtime_config_is_the_build_shape_and_hides_when_disabled(
    svc: SipConfigService,
) -> None:
    assert await svc.runtime_config() is None  # nothing configured

    await svc.set(**_base())  # type: ignore[arg-type]
    await svc.set_line(
        "1001", asterisk_endpoint="PJSIP/1001", label="", enabled=True, actor_id=None
    )
    cfg = await svc.runtime_config()
    assert cfg is not None
    assert cfg["gateway"] == {
        "kind": "asterisk_ari",
        "host": "pbx.bbz.internal",
        "port": 8088,
        "tls": True,
    }
    assert cfg["credentials"] == {"username": "bbz", "password": _PASSWORD}  # decrypted
    assert cfg["line_endpoints"] == {"1001": "PJSIP/1001"}
    assert cfg["app_name"] == "bbz-sip"

    await svc.set(**_base(enabled=False))  # type: ignore[arg-type]
    assert await svc.runtime_config() is None
