"""Read model for the audit log (roadmap E04-04).

Read-only. Filters on actor / target / action / time / correlation-id, keyset
pagination on ``(occurred_at_utc, id)`` so a concurrent append never shifts a
page. Scope filtering is a no-op hook (:meth:`_scope_filter`) until user
placement exists — wired in E23, same as the event queries.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent


@dataclass(frozen=True)
class AuditRow:
    id: uuid.UUID
    occurred_at_utc: _dt.datetime
    node_id: str
    action: str
    actor_user_id: uuid.UUID | None
    actor_client_id: str | None
    workplace_id: str | None
    target_type: str | None
    target_id: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    correlation_id: str | None
    event_seq_ref: int | None


@dataclass(frozen=True)
class AuditPage:
    items: list[AuditRow]
    next_cursor: str | None


def _cursor(at: _dt.datetime, rid: uuid.UUID) -> str:
    return f"{at.timestamp():.6f}|{rid}"


def _parse_cursor(raw: str) -> tuple[_dt.datetime, uuid.UUID]:
    ts, _, rid = raw.partition("|")
    return _dt.datetime.fromtimestamp(float(ts), tz=_dt.UTC), uuid.UUID(rid)


class AuditQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def _scope_filter(self, stmt: Select[tuple[AuditEvent]]) -> Select[tuple[AuditEvent]]:
        return stmt  # E23

    async def query(
        self,
        *,
        action: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        correlation_id: str | None = None,
        since: _dt.datetime | None = None,
        until: _dt.datetime | None = None,
        cursor: str | None = None,
        limit: int = 100,
    ) -> AuditPage:
        stmt = select(AuditEvent).order_by(AuditEvent.occurred_at_utc.desc(), AuditEvent.id.desc())
        if action is not None:
            stmt = stmt.where(AuditEvent.action == action)
        if actor_user_id is not None:
            stmt = stmt.where(AuditEvent.actor_user_id == actor_user_id)
        if target_type is not None:
            stmt = stmt.where(AuditEvent.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(AuditEvent.target_id == target_id)
        if correlation_id is not None:
            stmt = stmt.where(AuditEvent.correlation_id == correlation_id)
        if since is not None:
            stmt = stmt.where(AuditEvent.occurred_at_utc >= since)
        if until is not None:
            stmt = stmt.where(AuditEvent.occurred_at_utc <= until)
        if cursor is not None:
            c_at, c_id = _parse_cursor(cursor)
            stmt = stmt.where(
                or_(
                    AuditEvent.occurred_at_utc < c_at,
                    and_(AuditEvent.occurred_at_utc == c_at, AuditEvent.id < c_id),
                )
            )

        rows = list(
            (await self._s.execute(self._scope_filter(stmt).limit(limit + 1))).scalars().all()
        )
        nxt: str | None = None
        if len(rows) > limit:
            rows = rows[:limit]
            nxt = _cursor(rows[-1].occurred_at_utc, rows[-1].id)
        return AuditPage(
            items=[
                AuditRow(
                    id=r.id,
                    occurred_at_utc=r.occurred_at_utc,
                    node_id=r.node_id,
                    action=r.action,
                    actor_user_id=r.actor_user_id,
                    actor_client_id=r.actor_client_id,
                    workplace_id=r.workplace_id,
                    target_type=r.target_type,
                    target_id=r.target_id,
                    before=r.before,
                    after=r.after,
                    reason=r.reason,
                    correlation_id=r.correlation_id,
                    event_seq_ref=r.event_seq_ref,
                )
                for r in rows
            ],
            next_cursor=nxt,
        )
