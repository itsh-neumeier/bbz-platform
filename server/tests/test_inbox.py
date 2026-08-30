"""Provider-event inbox: dedupe, deterministic key, replay safety (E04-07)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.inbox import (
    IngestOutcome,
    derive_dedupe_key,
    ingest,
    mark_processed,
)
from bbz_core.infra.models.inbox import ProviderEventInbox


def test_derive_dedupe_key_uses_provider_event_id_when_present() -> None:
    assert derive_dedupe_key("cti", "abc-123", {"x": 1}) == "cti:abc-123"


def test_derive_dedupe_key_is_deterministic_without_id() -> None:
    k1 = derive_dedupe_key("cti", None, {"a": 1, "b": 2})
    k2 = derive_dedupe_key("cti", None, {"b": 2, "a": 1})
    assert k1 == k2 and k1.startswith("cti:sha256:")
    assert derive_dedupe_key("cti", None, {"a": 2}) != k1


async def _count(s: AsyncSession) -> int:
    return (await s.execute(select(func.count()).select_from(ProviderEventInbox))).scalar_one()


async def test_first_ingest_is_new_second_is_duplicate(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        r1 = await ingest(s, provider="cti", provider_event_id="evt-1", normalized={"kind": "ring"})
    async with s.begin():
        r2 = await ingest(s, provider="cti", provider_event_id="evt-1", normalized={"kind": "ring"})
    assert r1.outcome is IngestOutcome.NEW
    assert r2.outcome is IngestOutcome.DUPLICATE
    assert r2.inbox_id == r1.inbox_id
    assert await _count(s) == 1


async def test_replay_without_stable_id_dedupes_on_payload(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    payload = {"door": "A12", "state": "forced"}
    async with s.begin():
        first = await ingest(s, provider="siedle", normalized=payload)
    async with s.begin():
        replay = await ingest(s, provider="siedle", normalized=dict(reversed(payload.items())))
    assert first.outcome is IngestOutcome.NEW
    assert replay.outcome is IngestOutcome.DUPLICATE
    assert await _count(s) == 1


async def test_different_events_are_both_new(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        a = await ingest(s, provider="dwd", provider_event_id="w1", normalized={"sev": 3})
        b = await ingest(s, provider="dwd", provider_event_id="w2", normalized={"sev": 2})
    assert a.outcome is b.outcome is IngestOutcome.NEW
    assert await _count(s) == 2


async def test_mark_processed_is_idempotent(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        r = await ingest(s, provider="cti", provider_event_id="p1", normalized={})
    async with s.begin():
        await mark_processed(s, r.inbox_id)
        row = await s.get(ProviderEventInbox, r.inbox_id)
        assert row is not None
        first_ts = row.processed_at
    assert first_ts is not None

    async with s.begin():
        await mark_processed(s, r.inbox_id)  # no-op, keeps the original timestamp
        again = await s.get(ProviderEventInbox, r.inbox_id)
    assert again is not None and again.processed_at == first_ts
