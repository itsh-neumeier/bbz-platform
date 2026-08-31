"""Normalized inbound signal: telephony mapper (pure) + inbox hand-off (E15-04)."""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.triggers import (
    InboundSignalRejected,
    from_telephony_event,
    validate_inbound_signal,
)
from bbz_core.infra.inbound_signals import record_inbound_signal
from bbz_core.infra.models.inbox import ProviderEventInbox


def _tel(**kw: Any) -> dict[str, Any]:
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "telephony_event_id": f"t-{uuid.uuid4().hex[:8]}",
        "provider": "telephony_mock",
        "raw_event_type": "Mock",
        "event_type": "CALL_RINGING",
        "source_call_id": "c-1",
        "calling_number": "+49911500123",
        "called_number": "110",
        "occurred_at": now,
        "received_at": now,
        "gateway_node": "BBZ-SRV01",
    }
    base.update(kw)
    return base


# --- pure mapper ---------------------------------------------------------


def test_a_ringing_call_maps_to_a_call_ringing_signal() -> None:
    signal = from_telephony_event(_tel(event_type="CALL_RINGING"))
    assert signal is not None
    validate_inbound_signal(signal)  # must already be valid
    assert signal["signal_type"] == "CALL_RINGING"
    assert signal["provider"] == "telephony_mock"
    assert signal["source"]["ani"] == "+49911500123"
    assert signal["source"]["dnis"] == "110"


def test_disconnect_and_fail_map_to_call_ended() -> None:
    for et in ("CALL_DISCONNECTED", "CALL_FAILED"):
        assert from_telephony_event(_tel(event_type=et))["signal_type"] == "CALL_ENDED"


def test_line_and_cti_events_are_not_signals() -> None:
    for et in ("LINE_IN_SERVICE", "CTI_PROVIDER_OUT_OF_SERVICE", "DEVICE_REGISTERED"):
        assert from_telephony_event(_tel(event_type=et, source_call_id=None)) is None


def test_only_allowlisted_metadata_is_carried() -> None:
    signal = from_telephony_event(
        _tel(
            metadata={
                "direction": "inbound",
                "cti_route_point": "RP_9",
                "technical_endpoint_id": "ep-42",
                "cisco_secret_handle": "0xDEAD",
            }
        )
    )
    assert signal is not None
    src = signal["source"]
    assert src["direction"] == "inbound"
    assert src["cti_route_point"] == "RP_9"
    assert src["technical_endpoint_id"] == "ep-42"
    assert "cisco_secret_handle" not in src
    assert "cisco_secret_handle" not in str(signal)


def test_validate_rejects_a_vendor_field() -> None:
    with pytest.raises(InboundSignalRejected):
        validate_inbound_signal(
            {
                "signal_type": "CALL_RINGING",
                "provider": "x",
                "occurred_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "received_at": _dt.datetime.now(_dt.UTC).isoformat(),
                "gateway_node": "n",
                "source": {},
                "raw": {"vendor": "stuff"},
            }
        )


# --- inbox hand-off ----------------------------------------------------


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def test_record_inbound_signal_dedupes(s: AsyncSession) -> None:
    signal = from_telephony_event(_tel(event_type="CALL_RINGING"))
    assert signal is not None

    async with s.begin():
        first = await record_inbound_signal(s, signal=signal, provider_event_id="evt-1")
    async with s.begin():
        second = await record_inbound_signal(s, signal=signal, provider_event_id="evt-1")

    assert first.outcome.value == "new"
    assert second.outcome.value == "duplicate"
    assert first.inbox_id == second.inbox_id

    rows = (await s.execute(select(ProviderEventInbox))).scalars().all()
    assert len(rows) == 1
    assert rows[0].normalized["signal_type"] == "CALL_RINGING"
    # the stored payload is the signal — no raw provider fields
    assert "telephony_event_id" not in rows[0].normalized


async def test_record_inbound_signal_rejects_an_invalid_signal(s: AsyncSession) -> None:
    with pytest.raises(InboundSignalRejected):
        async with s.begin():
            await record_inbound_signal(s, signal={"signal_type": "CALL_RINGING"})
