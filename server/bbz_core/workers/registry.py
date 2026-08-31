"""The named cluster-wide singletons every node starts (roadmap E06-06).

Each singleton runs on **every** node but does work only on the node that
currently holds its etcd lease (ADR-0018) — so background work never runs
twice. ``/cluster/status.leaders`` shows the holder per name; a failover moves
it within ``2 * ttl`` (``run_as_singleton`` steps down the instant a lease
renewal fails and the new leader campaigns on the next cycle).

``do_work`` is one **tick**, not a loop: :func:`run_as_singleton` calls it once
per cycle while leader.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

#: leader-election names, also the keys under ``/bbz/leader/`` in etcd.
SINGLETON_NAMES: tuple[str, ...] = ("outbox-dispatcher", "workflow-timer", "trigger-engine")


@dataclass(frozen=True)
class Singleton:
    name: str
    tick: Callable[[], Awaitable[object]]


async def _outbox_tick() -> object:
    from bbz_core.workers.outbox_dispatcher import OutboxDispatcher

    return await OutboxDispatcher().run_once()


async def _workflow_timer_tick() -> object:
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.repositories.workflow_engine import WorkflowEngineService

    async with session_scope() as session:
        return await WorkflowEngineService(session).fire_due_timers()


async def _trigger_engine_tick() -> object:
    """Drain the provider inbox: run every unprocessed inbound signal through the
    trigger engine, exactly once (E15-15 / ADR-0024)."""
    from bbz_core.infra.db import session_scope
    from bbz_core.infra.repositories.trigger_engine import TriggerEngine

    async with session_scope() as session:
        results = await TriggerEngine(session).resume_unprocessed()
        return len(results)


def cluster_singletons() -> list[Singleton]:
    return [
        Singleton("outbox-dispatcher", _outbox_tick),
        Singleton("workflow-timer", _workflow_timer_tick),
        Singleton("trigger-engine", _trigger_engine_tick),
    ]
