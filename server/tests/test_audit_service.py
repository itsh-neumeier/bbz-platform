"""Audit-write service: in-TX atomicity, reason enforcement, diff helper (E04-02)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.audit import (
    AuditAction,
    AuditNotInTransactionError,
    AuditReasonRequiredError,
    AuditService,
    changed_fields,
)
from bbz_core.infra.models.audit import AuditEvent


def test_changed_fields_reports_only_real_changes() -> None:
    diff = changed_fields({"a": 1, "b": "x", "c": None}, {"a": 1, "b": "y", "d": True})
    assert diff == {
        "b": {"from": "x", "to": "y"},
        "d": {"from": None, "to": True},
    }  # a unchanged; c is None on both sides


def test_changed_fields_handles_none() -> None:
    assert changed_fields(None, None) == {}
    assert changed_fields(None, {"x": 1}) == {"x": {"from": None, "to": 1}}


async def _count(s: AsyncSession) -> int:
    return (await s.execute(select(func.count()).select_from(AuditEvent))).scalar_one()


async def test_write_requires_a_transaction(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(AuditNotInTransactionError):
        await AuditService(s).write(AuditAction.EVENT_ARCHIVED, target_type="event")
    assert await _count(s) == 0


async def test_write_commits_with_the_caller_transaction(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        await AuditService(s).write(
            AuditAction.EVENT_ARCHIVED,
            actor_user_id=uuid.uuid4(),
            target_type="event",
            target_id=str(uuid.uuid4()),
            before={"status": "opened"},
            after={"status": "archived"},
        )
    assert await _count(s) == 1


async def test_write_rolls_back_with_the_caller_transaction(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(RuntimeError, match="boom"):
        async with s.begin():
            await AuditService(s).write(AuditAction.EVENT_ARCHIVED, target_type="event")
            raise RuntimeError("boom")
    assert await _count(s) == 0


async def test_reason_is_mandatory_for_flagged_actions(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    with pytest.raises(AuditReasonRequiredError):
        async with s.begin():
            await AuditService(s).write(
                AuditAction.EVENT_REACTIVATED, target_type="event", reason="   "
            )
    assert await _count(s) == 0
    await s.rollback()

    async with s.begin():
        await AuditService(s).write(
            AuditAction.EVENT_REACTIVATED, target_type="event", reason="Rückfrage BPol"
        )
    row = (await s.execute(select(AuditEvent))).scalar_one()
    assert row.reason == "Rückfrage BPol"
