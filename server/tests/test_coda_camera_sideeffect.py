"""Camera opening is a decoupled outbox side effect (roadmap E16-08): the
open_camera / open_camera_group outbox handler reaches the video.* provider;
a provider that is down retries with backoff and, at the attempt cap, records
the row failed + notes CAMERA_ACTION_FAILED on the triggering event — the event
itself stays active. No double open.

A *successful* delivery that carried an event_id notes CAMERA_OPENED on the
event instead, so the operator camera panel can list the associated cameras
(E16-12 / ADR-0032).
"""

from __future__ import annotations

import datetime as _dt
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.db import get_sessionmaker
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.outbox import ExternalActionOutbox
from bbz_core.infra.outbox import enqueue
from bbz_core.integrations_host.providers import reset_provider_cache
from bbz_core.workers import camera_handlers
from bbz_core.workers.outbox_dispatcher import DEFAULT_HANDLERS, OutboxDispatcher

_EVENT_ID = str(uuid.uuid4())


@pytest.fixture
async def s(db: object) -> AsyncIterator[AsyncSession]:
    assert isinstance(db, AsyncSession)
    yield db


@pytest.fixture(autouse=True)
def _clean_provider_cache() -> Iterator[None]:
    reset_provider_cache()
    yield
    reset_provider_cache()


def _dispatcher() -> OutboxDispatcher:
    return OutboxDispatcher({**DEFAULT_HANDLERS, **camera_handlers.CAMERA_HANDLERS})


async def _enqueue_group(s: AsyncSession, *, dedupe: str, event_id: str | None = _EVENT_ID) -> None:
    payload: dict[str, Any] = {
        "camera_refs": ["CAM-1", "CAM-2"],
        "command_id": dedupe,
    }
    if event_id is not None:
        payload["event_id"] = event_id
    async with s.begin():
        await enqueue(s, dedupe_key=dedupe, action_type="open_camera_group", payload=payload)


async def _row(s: AsyncSession) -> ExternalActionOutbox:
    await s.rollback()
    return (await s.execute(select(ExternalActionOutbox))).scalar_one()


async def test_the_handler_opens_the_group_via_the_video_provider(s: AsyncSession) -> None:
    await _enqueue_group(s, dedupe="trigger:e:v:0")

    disp = _dispatcher()
    assert await disp.run_once() == 1
    assert await disp.run_once() == 0  # exactly once

    row = await _row(s)
    assert row.status == "dispatched"
    assert row.result["camera_ids"] == ["CAM-1", "CAM-2"]
    audited = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EXTERNAL_ACTION_DISPATCHED")
        )
    ).scalar_one()
    assert audited == 1

    # E16-12 / ADR-0032: the successful open is recorded on the event, once
    opened = (
        (await s.execute(select(DomainEvent).where(DomainEvent.event_type == "CAMERA_OPENED")))
        .scalars()
        .all()
    )
    assert len(opened) == 1
    assert opened[0].aggregate_id == _EVENT_ID
    assert opened[0].payload["camera_refs"] == ["CAM-1", "CAM-2"]
    assert opened[0].payload["action_type"] == "open_camera_group"


async def test_no_camera_opened_note_when_the_action_carries_no_event_id(s: AsyncSession) -> None:
    await _enqueue_group(s, dedupe="trigger:e:v:9", event_id=None)
    assert await _dispatcher().run_once() == 1

    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "CAMERA_OPENED")
        )
    ).scalar_one() == 0


async def test_a_provider_that_is_down_retries_then_fails_and_notes_the_event(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bbz_integration_sdk.providers.video_types import VideoProviderError

    async def _down() -> Any:
        raise VideoProviderError("coda unreachable")

    monkeypatch.setattr(camera_handlers, "active_video_provider", _down)

    await _enqueue_group(s, dedupe="trigger:e:v:1")
    disp = _dispatcher()

    await disp.run_once()  # attempt 1 -> retry
    async with get_sessionmaker()() as r:
        row = (await r.execute(select(ExternalActionOutbox))).scalar_one()
    assert row.status == "pending" and row.attempts == 1
    assert row.next_attempt_at > _dt.datetime.now(_dt.UTC)

    for _ in range(20):
        async with get_sessionmaker()() as w, w.begin():
            cur = (await w.execute(select(ExternalActionOutbox))).scalar_one()
            if cur.status == "failed":
                break
            cur.next_attempt_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=1)
        await disp.run_once()

    async with get_sessionmaker()() as r2:
        final = (await r2.execute(select(ExternalActionOutbox))).scalar_one()
    assert final.status == "failed" and "coda unreachable" in (final.last_error or "")

    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EXTERNAL_ACTION_FAILED")
        )
    ).scalar_one() == 1
    # the failure is recorded on the triggering event, once
    notes = (
        (
            await s.execute(
                select(DomainEvent).where(DomainEvent.event_type == "CAMERA_ACTION_FAILED")
            )
        )
        .scalars()
        .all()
    )
    assert len(notes) == 1
    assert notes[0].aggregate_id == _EVENT_ID
    assert notes[0].payload["camera_refs"] == ["CAM-1", "CAM-2"]
    assert notes[0].payload["action_type"] == "open_camera_group"


async def test_no_event_note_when_the_action_carries_no_event_id(
    s: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bbz_integration_sdk.providers.video_types import VideoProviderError

    async def _down() -> Any:
        raise VideoProviderError("down")

    monkeypatch.setattr(camera_handlers, "active_video_provider", _down)
    await _enqueue_group(s, dedupe="trigger:e:v:2", event_id=None)
    disp = _dispatcher()

    for _ in range(20):
        async with get_sessionmaker()() as w, w.begin():
            cur = (await w.execute(select(ExternalActionOutbox))).scalar_one()
            if cur.status == "failed":
                break
            cur.next_attempt_at = _dt.datetime.now(_dt.UTC) - _dt.timedelta(seconds=1)
        await disp.run_once()

    await s.rollback()
    assert (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "CAMERA_ACTION_FAILED")
        )
    ).scalar_one() == 0


async def test_a_replayed_dispatch_never_opens_twice(s: AsyncSession) -> None:
    calls: list[str] = []
    real = camera_handlers.open_camera_group

    async def _counting(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append(payload["command_id"])
        return await real(payload)

    disp = OutboxDispatcher({**DEFAULT_HANDLERS, "open_camera_group": _counting})
    await _enqueue_group(s, dedupe="trigger:e:v:3")

    assert await disp.run_once() == 1
    assert await disp.run_once() == 0  # row already dispatched -> not re-run
    assert calls == ["trigger:e:v:3"]
