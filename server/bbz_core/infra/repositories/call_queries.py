"""Call history read model (roadmap E11-11).

Read-only. ``GET /calls`` — filter by time / direction / number / category /
state, keyset-paginated on ``(created_at, id)`` descending so a new call never
shifts a page. Scope filtering (a user only sees permitted BBZ/workplaces) is a
no-op hook until user placement exists (E23), same as the event queries.

Numbers and free text are personally identifiable — ``calls.view_history`` and
scope gate this.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.telephony import Call, CallDocumentation, CallParticipant


@dataclass(frozen=True)
class ParticipantItem:
    number: str | None
    display_name: str | None
    role: str


@dataclass(frozen=True)
class CallHistoryItem:
    id: uuid.UUID
    bbz_call_id: str
    provider: str
    direction: str
    state: str
    line_id: uuid.UUID | None
    workplace_id: uuid.UUID | None
    started_at: _dt.datetime | None
    ended_at: _dt.datetime | None
    created_at: _dt.datetime
    category: str | None
    has_free_text: bool
    participants: list[ParticipantItem] = field(default_factory=list)


@dataclass(frozen=True)
class CallHistoryPage:
    items: list[CallHistoryItem]
    next_cursor: str | None


def _cursor(at: _dt.datetime, rid: uuid.UUID) -> str:
    return f"{at.timestamp():.6f}|{rid}"


def _parse_cursor(raw: str) -> tuple[_dt.datetime, uuid.UUID]:
    ts, _, rid = raw.partition("|")
    return _dt.datetime.fromtimestamp(float(ts), tz=_dt.UTC), uuid.UUID(rid)


class CallQueryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    def _scope_filter(self, stmt: Select[tuple[Call]]) -> Select[tuple[Call]]:
        return stmt  # E23

    async def history(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        direction: str | None = None,
        state: str | None = None,
        number: str | None = None,
        category: str | None = None,
        since: _dt.datetime | None = None,
        until: _dt.datetime | None = None,
    ) -> CallHistoryPage:
        stmt = select(Call).order_by(Call.created_at.desc(), Call.id.desc())
        if direction is not None:
            stmt = stmt.where(Call.direction == direction)
        if state is not None:
            stmt = stmt.where(Call.state == state)
        if since is not None:
            stmt = stmt.where(Call.created_at >= since)
        if until is not None:
            stmt = stmt.where(Call.created_at <= until)
        if number is not None:
            stmt = stmt.where(
                Call.id.in_(select(CallParticipant.call_id).where(CallParticipant.number == number))
            )
        if category is not None:
            stmt = stmt.where(
                Call.id.in_(
                    select(CallDocumentation.call_id).where(CallDocumentation.category == category)
                )
            )
        if cursor is not None:
            c_at, c_id = _parse_cursor(cursor)
            stmt = stmt.where(
                or_(
                    Call.created_at < c_at,
                    and_(Call.created_at == c_at, Call.id < c_id),
                )
            )

        calls = list(
            (await self._s.execute(self._scope_filter(stmt.limit(limit + 1)))).scalars().all()
        )
        nxt: str | None = None
        if len(calls) > limit:
            calls = calls[:limit]
            nxt = _cursor(calls[-1].created_at, calls[-1].id)

        call_ids = [c.id for c in calls]
        parts = await self._participants(call_ids)
        docs = await self._docs(call_ids)
        return CallHistoryPage(
            items=[
                CallHistoryItem(
                    id=c.id,
                    bbz_call_id=c.bbz_call_id,
                    provider=c.provider,
                    direction=c.direction,
                    state=c.state,
                    line_id=c.line_id,
                    workplace_id=c.workplace_id,
                    started_at=c.started_at,
                    ended_at=c.ended_at,
                    created_at=c.created_at,
                    category=docs.get(c.id, (None, False))[0],
                    has_free_text=docs.get(c.id, (None, False))[1],
                    participants=parts.get(c.id, []),
                )
                for c in calls
            ],
            next_cursor=nxt,
        )

    async def _participants(
        self, call_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[ParticipantItem]]:
        if not call_ids:
            return {}
        rows = (
            (
                await self._s.execute(
                    select(CallParticipant)
                    .where(CallParticipant.call_id.in_(call_ids))
                    .order_by(CallParticipant.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        out: dict[uuid.UUID, list[ParticipantItem]] = {}
        for p in rows:
            out.setdefault(p.call_id, []).append(
                ParticipantItem(number=p.number, display_name=p.display_name, role=p.role)
            )
        return out

    async def _docs(self, call_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[str | None, bool]]:
        if not call_ids:
            return {}
        rows = (
            (
                await self._s.execute(
                    select(CallDocumentation).where(CallDocumentation.call_id.in_(call_ids))
                )
            )
            .scalars()
            .all()
        )
        return {d.call_id: (d.category, (d.free_text or "") != "") for d in rows}
