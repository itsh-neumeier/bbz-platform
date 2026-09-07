"""sip_gateway / sip_lines schema (E13-07, ADR-0033)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.sip_gateway import SipGateway, SipLine


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def test_gateway_server_defaults(s: AsyncSession) -> None:
    g = SipGateway(instance_id="sip")
    s.add(g)
    await s.flush()
    assert g.kind == "asterisk_ari"
    assert g.port == 8088 and g.tls is True
    assert g.app_name == "bbz-sip" and g.dtmf_transport == "rfc2833"
    assert g.ari_username == "" and g.ari_password_ciphertext == ""
    assert g.enabled is False


async def test_line_endpoint_and_cascade_delete(s: AsyncSession) -> None:
    s.add(SipGateway(instance_id="sip"))
    await s.flush()
    s.add(SipLine(bbz_line_id="1001", gateway_instance_id="sip", asterisk_endpoint="PJSIP/1001"))
    await s.flush()

    # dropping the gateway takes its lines with it (ON DELETE CASCADE)
    await s.delete(await s.get(SipGateway, "sip"))
    await s.flush()
    assert (await s.execute(select(SipLine))).scalars().all() == []
