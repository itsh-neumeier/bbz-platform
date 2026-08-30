"""Leader election: local backend, etcd lease, singleton runner (E04-08)."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from bbz_core.infra.leader import (
    EtcdLeaderElection,
    LeaderElection,
    LocalLeaderElection,
)
from bbz_core.workers.singleton import run_as_singleton

_ETCD = "http://localhost:2379"


async def _etcd_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.0) as c:
            r = await c.post(f"{_ETCD}/v3/maintenance/status", json={})
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def test_local_backend_is_always_leader() -> None:
    el = LocalLeaderElection("x")
    assert await el.acquire() is True
    assert await el.renew() is True
    await el.resign()


def _etcd(name: str, node: str) -> EtcdLeaderElection:
    return EtcdLeaderElection(
        name, node_id=node, endpoints=[_ETCD], ttl_seconds=5, prefix="/bbz-test/leader"
    )


async def test_etcd_only_one_leader_and_handoff_on_resign() -> None:
    if not await _etcd_up():
        pytest.skip("no etcd on localhost:2379")
    name = f"disp-{uuid.uuid4().hex[:8]}"
    a, b = _etcd(name, "node-a"), _etcd(name, "node-b")
    try:
        assert await a.acquire() is True
        assert await b.acquire() is False  # a holds it
        assert await a.renew() is True

        await a.resign()
        assert await b.acquire() is True  # handoff
        assert await a.acquire() is False
    finally:
        await a.aclose()
        await b.aclose()


class _FakeElection(LeaderElection):
    def __init__(self) -> None:
        self.name = "fake"
        self.acquired = 0
        self.resigned = 0
        self._renews_left = 2

    async def acquire(self) -> bool:
        self.acquired += 1
        return True

    async def renew(self) -> bool:
        self._renews_left -= 1
        return self._renews_left >= 0

    async def resign(self) -> None:
        self.resigned += 1


async def test_run_as_singleton_works_while_leader_then_steps_down(db: object) -> None:
    # `db` gives a real schema so the WORKER_LEADER_CHANGED audit writes cleanly
    # (and the fixture disposes the engine afterwards).
    assert db is not None
    el = _FakeElection()
    calls = 0
    stop = asyncio.Event()

    async def work() -> None:
        nonlocal calls
        calls += 1
        if calls >= 3:
            stop.set()

    await asyncio.wait_for(run_as_singleton(el, work, ttl_seconds=1, stop=stop), timeout=10)
    assert calls >= 1
    assert el.acquired >= 1
