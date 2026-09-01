"""Named cluster singletons: registry + leader-only execution (E06-06)."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.workers import manager
from bbz_core.workers.registry import SINGLETON_NAMES, Singleton, cluster_singletons


def test_the_registry_lists_the_expected_singletons() -> None:
    names = [s.name for s in cluster_singletons()]
    assert names == list(SINGLETON_NAMES)
    assert set(names) == {
        "outbox-dispatcher",
        "workflow-timer",
        "trigger-engine",
        "weather-refresh",
        "directory-sync",
    }


async def test_the_real_ticks_run_against_the_database(
    db: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    # weather-refresh would poll DWD over the network — point it at nothing so the
    # tick is a no-op (CI must not touch the network, ADR-0026)
    from bbz_core import settings as settings_mod

    monkeypatch.setenv("BBZ_WEATHER_INTEGRATION_ID", "none")
    settings_mod.get_settings.cache_clear()

    # every tick opens its own session and is safe on an empty system
    for spec in cluster_singletons():
        assert isinstance(await spec.tick(), int)  # rows handled / timers fired / signals drained

    settings_mod.get_settings.cache_clear()


async def test_cluster_workers_run_the_leader_and_stop_cleanly(
    db: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert db is not None  # real schema for the WORKER_LEADER_CHANGED audit
    from bbz_core import settings as settings_mod

    monkeypatch.setenv("BBZ_WORKER_LEADER_TTL_SECONDS", "1")
    settings_mod.get_settings.cache_clear()

    calls = {"a": 0, "b": 0}

    async def tick_a() -> None:
        calls["a"] += 1

    async def tick_b() -> None:
        calls["b"] += 1

    monkeypatch.setattr(
        manager,
        "cluster_singletons",
        lambda: [Singleton("test-a", tick_a), Singleton("test-b", tick_b)],
    )

    workers = manager.ClusterWorkers()
    await workers.start()
    try:
        await asyncio.sleep(0.6)
    finally:
        await workers.stop()

    assert calls["a"] >= 1 and calls["b"] >= 1
    assert workers._tasks == []  # stop() drained everything


async def test_cluster_status_lists_the_singletons(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    from bbz_core.infra.cluster_status import gather_status

    status = await gather_status(s)
    assert status["singletons"] == list(SINGLETON_NAMES)
    assert status["stub"] is False
