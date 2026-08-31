"""Alarm normalization -> immutable provider event -> inbox dedupe (E16-04).

Pure-mapper tests plus the inbox hand-off, driven both with hand-built dicts and
through the E16-03 ``coda_video`` mock exactly as the E16-07 runtime flow will.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.triggers import (
    AlarmEventRejected,
    alarm_event_dedupe_key,
    normalize_alarm_event,
)
from bbz_core.infra.alarm_ingest import ingest_alarm_event
from bbz_core.infra.models.inbox import ProviderEventInbox
from integrations.coda_video.adapter import MockCodaVideoProvider


def _incoming(**kw: Any) -> dict[str, Any]:
    """An ``IncomingAlarm.model_dump(mode="json")`` shape."""
    now = _dt.datetime.now(_dt.UTC).isoformat()
    base: dict[str, Any] = {
        "provider": "coda_video",
        "provider_instance_id": "coda-mock-1",
        "provider_event_id": "CODA-EVT-4711",
        "provider_alarm_id": None,
        "alarm_type": "panic",
        "alarm_subtype": "panic_button",
        "source_external_id": "CODA-ALARM-4711",
        "source_name": "Ueberfalltaster ServicePoint Nuernberg Hbf",
        "site_external_id": "Nuernberg Hbf",
        "occurred_at": now,
        "received_at": now,
        "severity_external": "critical",
        "state_external": "active",
        "associated_camera_ids": ["CAM-SP-NBG-02", "CAM-SP-NBG-01"],
        "raw": {"id": "CODA-EVT-4711", "vendor_secret": "0xDEAD", "cameras": ["CAM-SP-NBG-01"]},
    }
    base.update(kw)
    return base


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


async def _alarm_rows(s: AsyncSession) -> list[ProviderEventInbox]:
    """Inbox rows for the immutable alarm event — not the queued ``signal:`` row
    the trigger engine drains (E16-07)."""
    await s.rollback()
    rows = (await s.execute(select(ProviderEventInbox))).scalars().all()
    return [r for r in rows if not r.dedupe_key.startswith("signal:")]


async def _signal_rows(s: AsyncSession) -> list[ProviderEventInbox]:
    await s.rollback()
    rows = (await s.execute(select(ProviderEventInbox))).scalars().all()
    return [r for r in rows if r.dedupe_key.startswith("signal:")]


# --- pure normalization ------------------------------------------------


def test_normalization_drops_the_raw_payload_and_keeps_only_its_hash() -> None:
    event = normalize_alarm_event(_incoming())
    assert "raw" not in event
    assert "vendor_secret" not in str(event)
    assert len(event["raw_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in event["raw_hash"])
    # camera ids are normalized (sorted, de-duplicated)
    assert event["associated_camera_ids"] == ["CAM-SP-NBG-01", "CAM-SP-NBG-02"]
    assert event["provider_event_id"] == "CODA-EVT-4711"


def test_a_vendor_field_in_the_incoming_alarm_is_dropped_not_carried() -> None:
    event = normalize_alarm_event({**_incoming(), "cisco_handle": "0xDEAD", "coda_zone": "west"})
    assert "cisco_handle" not in event
    assert "coda_zone" not in event
    assert "0xDEAD" not in str(event)


def test_normalization_requires_the_mandatory_fields() -> None:
    with pytest.raises(AlarmEventRejected):
        normalize_alarm_event({**_incoming(), "source_external_id": ""})
    with pytest.raises(AlarmEventRejected):
        normalize_alarm_event({**_incoming(), "alarm_type": None})


def test_missing_stable_id_yields_a_deterministic_derived_id() -> None:
    fixed = {"provider_event_id": None, "occurred_at": "2026-08-31T09:15:00+00:00"}
    a = normalize_alarm_event(_incoming(**fixed))
    b = normalize_alarm_event(_incoming(**fixed))
    assert a["provider_event_id"] == b["provider_event_id"]
    assert a["provider_event_id"].startswith("derived:")
    # a different occurrence time is a different event
    c = normalize_alarm_event(
        _incoming(provider_event_id=None, occurred_at="2020-01-01T00:00:00+00:00")
    )
    assert c["provider_event_id"] != a["provider_event_id"]


def test_the_dedupe_key_is_provider_scoped() -> None:
    assert alarm_event_dedupe_key(normalize_alarm_event(_incoming())) == "coda_video:CODA-EVT-4711"


# --- inbox dedupe ----------------------------------------------------


async def test_a_duplicated_alarm_is_ingested_once(s: AsyncSession) -> None:
    incoming = _incoming()
    async with s.begin():
        first = await ingest_alarm_event(s, incoming)
    async with s.begin():
        second = await ingest_alarm_event(s, incoming)  # provider reconnect replay

    assert first.outcome.value == "new"
    assert second.outcome.value == "duplicate"
    assert first.inbox_id == second.inbox_id

    rows = await _alarm_rows(s)
    assert len(rows) == 1
    row = rows[0]
    assert row.normalized["provider_event_id"] == "CODA-EVT-4711"
    assert row.raw_hash == row.normalized["raw_hash"]
    assert "raw" not in row.normalized
    assert "vendor_secret" not in str(row.normalized)
    # exactly one inbound signal is queued for the trigger engine (E16-07)
    assert len(await _signal_rows(s)) == 1


async def test_two_distinct_alarms_are_two_rows(s: AsyncSession) -> None:
    async with s.begin():
        await ingest_alarm_event(s, _incoming(provider_event_id="E-1"))
    async with s.begin():
        await ingest_alarm_event(s, _incoming(provider_event_id="E-2"))
    assert len(await _alarm_rows(s)) == 2
    assert len(await _signal_rows(s)) == 2


async def test_replay_without_a_stable_id_still_dedupes(s: AsyncSession) -> None:
    incoming = _incoming(provider_event_id=None)
    async with s.begin():
        first = await ingest_alarm_event(s, incoming)
    async with s.begin():
        second = await ingest_alarm_event(s, incoming)
    assert first.outcome.value == "new"
    assert second.outcome.value == "duplicate"
    # the provider had no stable id -> the inbox column is NULL, the dedupe_key carries it
    rows = await _alarm_rows(s)
    assert len(rows) == 1
    assert rows[0].provider_event_id is None
    assert rows[0].dedupe_key.startswith("coda_video:derived:")


async def test_a_vendor_field_makes_no_row_difference(s: AsyncSession) -> None:
    async with s.begin():
        first = await ingest_alarm_event(s, _incoming())
    async with s.begin():
        second = await ingest_alarm_event(s, {**_incoming(), "cisco_handle": "x"})
    assert first.outcome.value == "new"
    assert second.outcome.value == "duplicate"  # the stray field does not change identity


async def test_the_e16_03_mock_alarm_flows_through(s: AsyncSession) -> None:
    p = MockCodaVideoProvider(
        simulated_sources=[
            {"external_source_id": "CODA-ALARM-4711", "name": "SP Nbg", "cameras": ["CAM-1"]}
        ]
    )
    p.simulate_alarm(
        {"id": "e-flow-1", "source": "CODA-ALARM-4711", "subtype": "panic_button", "type": "panic"}
    )
    alarms = [a async for a in p.subscribe_alarms()]
    assert len(alarms) == 1

    async with s.begin():
        result = await ingest_alarm_event(s, alarms[0].model_dump(mode="json"))

    assert result.outcome.value == "new"
    rows = await _alarm_rows(s)
    assert len(rows) == 1
    assert rows[0].normalized["alarm_subtype"] == "panic_button"
    assert rows[0].normalized["source_external_id"] == "CODA-ALARM-4711"
    assert rows[0].provider == "coda_video"
