"""Exactly-once / catch-up consistency suite (E04-11, MASTER_PROMPT §24, ADR-0011).

Covers the three failure shapes the platform must survive without losing or
double-applying anything:

* event catch-up by ``event_seq`` after a "connection drop";
* the same provider event delivered twice;
* the outbox worker killed mid-dispatch.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.db import get_sessionmaker
from bbz_core.infra.event_log import append_event, read_since
from bbz_core.infra.inbox import IngestOutcome, ingest, mark_processed
from bbz_core.infra.models.inbox import ProviderEventInbox
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.outbox import enqueue
from bbz_core.workers.outbox_dispatcher import OutboxDispatcher


def _payload() -> dict[str, str]:
    return {"from": "new", "to": "accepted", "actor_id": str(uuid.uuid4())}


async def _emit(s: AsyncSession, n: int) -> list[int]:
    seqs: list[int] = []
    for _ in range(n):
        async with s.begin():
            seqs.append(
                await append_event(
                    s,
                    aggregate_type="event",
                    aggregate_id=uuid.uuid4(),
                    event_type="EVENT_ACCEPTED",
                    payload=_payload(),
                )
            )
    return seqs


async def test_catch_up_after_a_drop_loses_and_duplicates_nothing(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)

    async def read_seqs(after: int, limit: int) -> list[int]:
        seqs = [r.event_seq for r in await read_since(s, after, limit=limit)]
        await s.rollback()  # close the read tx before the next write
        return seqs

    first_batch = await _emit(s, 5)

    # client consumes the first 3, then "drops"
    seen = await read_seqs(0, 3)
    assert seen == first_batch[:3]
    last_ack = seen[-1]

    # more events happen while the client is offline
    offline_batch = await _emit(s, 4)

    # reconnect from the last acked seq
    caught_up: list[int] = []
    cursor = last_ack
    while batch := await read_seqs(cursor, 2):
        caught_up.extend(batch)
        cursor = batch[-1]

    everything = first_batch + offline_batch
    assert seen + caught_up == everything  # order preserved, nothing lost
    assert len(set(seen + caught_up)) == len(everything)  # nothing duplicated


async def test_inbox_double_delivery_is_processed_once(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    processed: list[str] = []

    async def deliver() -> None:
        async with s.begin():
            res = await ingest(s, provider="cti", provider_event_id="ring-1", normalized={"n": 1})
            if res.outcome is IngestOutcome.NEW:
                processed.append(res.dedupe_key)
                await mark_processed(s, res.inbox_id)

    await deliver()
    await deliver()  # provider reconnect replay
    await deliver()

    assert processed == ["cti:ring-1"]
    assert (await s.execute(select(func.count()).select_from(ProviderEventInbox))).scalar_one() == 1


async def test_outbox_kill_mid_dispatch_ends_in_exactly_one_success(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    effects: list[str] = []
    attempts = 0

    async def flaky(payload: dict[str, object]) -> dict[str, object]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # side effect happened, then the worker is "killed" before commit
            raise RuntimeError("killed mid-dispatch")
        effects.append(str(payload["ref"]))
        return {"ok": True}

    async with s.begin():
        await enqueue(s, dedupe_key="k-kill", action_type="door", payload={"ref": "door-A12"})

    disp = OutboxDispatcher({"door": flaky})
    await disp.run_once()  # attempt 1 -> raises -> row back to pending
    async with get_sessionmaker()() as w, w.begin():
        r = (await w.execute(select(ExternalActionOutbox))).scalar_one()
        assert r.status == "pending" and r.attempts == 1
        r.next_attempt_at = r.created_at  # make it due again immediately
    await disp.run_once()  # attempt 2 -> success

    async with get_sessionmaker()() as r2:
        final = (await r2.execute(select(ExternalActionOutbox))).scalar_one()
    assert final.status == "dispatched"
    assert effects == ["door-A12"]  # exactly one committed side effect

    # a redundant run must not dispatch again
    await disp.run_once()
    assert effects == ["door-A12"]


async def test_concurrent_dispatchers_deliver_a_row_once(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    delivered: list[str] = []

    async def handler(payload: dict[str, object]) -> dict[str, object]:
        delivered.append(str(payload["ref"]))
        return {}

    async with s.begin():
        await enqueue(s, dedupe_key="k-conc", action_type="x", payload={"ref": "r1"})

    a, b = OutboxDispatcher({"x": handler}), OutboxDispatcher({"x": handler})
    await asyncio.gather(a.run_once(), b.run_once())
    assert delivered == ["r1"]
