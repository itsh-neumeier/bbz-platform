"""Run a coroutine as a cluster-wide singleton (ADR-0018, roadmap E04-08).

Campaigns for leadership via a :class:`bbz_core.infra.leader.LeaderElection`,
runs ``do_work`` only while leader, renews the lease each cycle, and steps down
the moment a renewal fails. Leadership changes are audited
(``WORKER_LEADER_CHANGED``).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from bbz_core.audit import AuditAction, AuditWriter
from bbz_core.infra.db import session_scope
from bbz_core.infra.leader import LeaderElection
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings

_log = get_logger(__name__)

DoWork = Callable[[], Awaitable[object]]


async def _audit_leader_change(election: str, is_leader: bool) -> None:
    with contextlib.suppress(Exception):
        async with session_scope() as session:
            await AuditWriter(session).record(
                AuditAction.WORKER_LEADER_CHANGED,
                target_type="worker",
                target_id=election,
                after={"leader": is_leader, "node_id": get_settings().node_id},
            )


async def run_as_singleton(
    election: LeaderElection,
    do_work: DoWork,
    *,
    ttl_seconds: int = 10,
    stop: asyncio.Event | None = None,
) -> None:  # pragma: no cover - exercised via integration
    """Loop until ``stop`` is set (or forever). Safe to start on every node."""
    is_leader = False
    renew_every = max(1.0, ttl_seconds / 3)
    try:
        while stop is None or not stop.is_set():
            if not is_leader:
                if await election.acquire():
                    is_leader = True
                    await _audit_leader_change(election.name, True)
                else:
                    await asyncio.sleep(ttl_seconds)
                    continue

            with contextlib.suppress(Exception):
                await do_work()

            if not await election.renew():
                is_leader = False
                await _audit_leader_change(election.name, False)
                continue
            await asyncio.sleep(renew_every)
    finally:
        if is_leader:
            await election.resign()
            await _audit_leader_change(election.name, False)
