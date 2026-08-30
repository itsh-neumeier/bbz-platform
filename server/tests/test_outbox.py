"""Transactional outbox + dispatcher: dedupe, exactly-once, retry/backoff (E04-06)."""

from __future__ import annotations

import datetime as _dt

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.outbox import NotInTransactionError, enqueue
from bbz_core.workers.outbox_dispatcher import OutboxDispatcher


async def _count(s: AsyncSession, **where: object) -> int:
    stmt = select(func.count()).select_from(ExternalActionOutbox)
    for k, v in where.items():
        stmt = stmt.where(getattr(ExternalActionOutbox, k) == v)
    return (await s.execute(stmt)).scalar_one()


async def test_enqueue_requires_a_transaction(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(NotInTransactionError):
        await enqueue(s, dedupe_key="k1", action_type="noop", payload={})


async def test_enqueue_dedupe_key_is_unique(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        assert await enqueue(s, dedupe_key="dk", action_type="noop", payload={"n": 1}) is True
    async with s.begin():
        assert await enqueue(s, dedupe_key="dk", action_type="noop", payload={"n": 2}) is False
    assert await _count(s, dedupe_key="dk") == 1


async def test_dispatcher_delivers_once_and_audits(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    calls: list[dict[str, object]] = []

    async def handler(payload: dict[str, object]) -> dict[str, object]:
        calls.append(payload)
        return {"ok": True}

    async with s.begin():
        await enqueue(s, dedupe_key="d1", action_type="ping", payload={"x": 1})

    disp = OutboxDispatcher({"ping": handler})
    assert await disp.run_once() == 1
    assert await disp.run_once() == 0  # nothing left to do -> exactly once
    assert calls == [{"x": 1}]

    row = (await s.execute(select(ExternalActionOutbox))).scalar_one()
    assert row.status == "dispatched" and row.attempts == 1 and row.result == {"ok": True}
    audited = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EXTERNAL_ACTION_DISPATCHED")
        )
    ).scalar_one()
    assert audited == 1


async def test_failing_handler_retries_with_backoff_then_fails(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)

    async def boom(_payload: dict[str, object]) -> dict[str, object]:
        raise RuntimeError("nope")

    async with s.begin():
        await enqueue(s, dedupe_key="d2", action_type="boom", payload={})

    disp = OutboxDispatcher({"boom": boom})

    from bbz_core.infra.db import get_sessionmaker

    await disp.run_once()  # attempt 1 -> retry, next_attempt_at in the future
    async with get_sessionmaker()() as r1:
        row = (await r1.execute(select(ExternalActionOutbox))).scalar_one()
    assert row.status == "pending" and row.attempts == 1
    assert row.next_attempt_at > _dt.datetime.now(_dt.UTC)
    assert "nope" in (row.last_error or "")

    # force it due and drive it to the attempt limit
    for _ in range(20):
        async with get_sessionmaker()() as w, w.begin():
            r = (await w.execute(select(ExternalActionOutbox))).scalar_one()
            if r.status == "failed":
                break
            r.next_attempt_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=1)
        await disp.run_once()

    async with get_sessionmaker()() as r2:
        final = (await r2.execute(select(ExternalActionOutbox))).scalar_one()
    assert final.status == "failed"
    failed_audit = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EXTERNAL_ACTION_FAILED")
        )
    ).scalar_one()
    assert failed_audit == 1


async def test_unknown_action_type_goes_straight_to_failed(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        await enqueue(s, dedupe_key="d3", action_type="does-not-exist", payload={})

    assert await OutboxDispatcher().run_once() == 1
    row = (await s.execute(select(ExternalActionOutbox))).scalar_one()
    assert row.status == "failed" and "no handler" in (row.last_error or "")
