"""Start / stop the cluster singletons as the app's background tasks (E06-06).

Wired into the FastAPI lifespan when ``BBZ_RUN_BACKGROUND_WORKERS`` is set. Every
node starts the same set; the leader election (etcd, or the always-leader local
backend in dev) decides which node actually does the work.
"""

from __future__ import annotations

import asyncio
import contextlib

from bbz_core.infra.leader import leader_election_for
from bbz_core.logging import get_logger
from bbz_core.settings import get_settings
from bbz_core.workers.registry import cluster_singletons
from bbz_core.workers.singleton import run_as_singleton

_log = get_logger(__name__)


class ClusterWorkers:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        ttl = get_settings().worker_leader_ttl_seconds
        for spec in cluster_singletons():
            election = leader_election_for(spec.name)
            self._tasks.append(
                asyncio.create_task(
                    run_as_singleton(election, spec.tick, ttl_seconds=ttl, stop=self._stop),
                    name=f"singleton:{spec.name}",
                )
            )
        _log.info("cluster_workers_started", singletons=[s.name for s in cluster_singletons()])

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        self._tasks.clear()
        _log.info("cluster_workers_stopped")
