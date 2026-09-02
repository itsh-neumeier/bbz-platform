"""Cluster-wide fixed-window rate limiting (roadmap E23-04, MASTER_PROMPT §22).

:class:`RateLimiter` does one indexed upsert per hit against ``rate_limit_hits``
(shared by both app nodes → the limit is enforced cluster-wide). A window is
``window_seconds`` wide; the count resets when it rolls over. Over the limit ⇒
``allowed=False`` and ``retry_after`` = seconds to the end of the window.
"""

from __future__ import annotations

import datetime as _dt
import math
from dataclasses import dataclass

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.rate_limit import RateLimitHit


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    retry_after: int


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


class RateLimiter:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def hit(self, rule: RateLimitRule, identifier: str) -> RateLimitResult:
        """Count one request against ``rule`` for ``identifier``. Commits the
        increment immediately (it must survive even the allowed path)."""
        now = _now()
        epoch = math.floor(now.timestamp() / rule.window_seconds) * rule.window_seconds
        window_start = _dt.datetime.fromtimestamp(epoch, _dt.UTC)
        expires_at = window_start + _dt.timedelta(seconds=rule.window_seconds)
        bucket = f"{rule.name}:{identifier}"[:160]

        stmt = (
            pg_insert(RateLimitHit)
            .values(bucket=bucket, window_start=window_start, count=1, expires_at=expires_at)
            .on_conflict_do_update(
                index_elements=["bucket", "window_start"],
                set_={"count": RateLimitHit.count + 1},
            )
            .returning(RateLimitHit.count)
        )
        await self._s.rollback()
        async with self._s.begin():
            count = (await self._s.execute(stmt)).scalar_one()
            if count == 1:  # first hit in this window — drop this bucket's stale rows
                await self._s.execute(
                    delete(RateLimitHit).where(
                        RateLimitHit.bucket == bucket, RateLimitHit.expires_at < now
                    )
                )
        retry_after = max(1, math.ceil((expires_at - now).total_seconds()))
        return RateLimitResult(allowed=count <= rule.limit, count=count, retry_after=retry_after)

    async def prune(self) -> int:
        """Drop every expired window row (for a future housekeeping worker)."""
        await self._s.rollback()
        async with self._s.begin():
            res = await self._s.execute(
                delete(RateLimitHit).where(RateLimitHit.expires_at < _now())
            )
        return int(getattr(res, "rowcount", 0) or 0)
