"""E22-05: GET /api/v1/integrations/health — the uniform view over every active
integration (state / last-ok / last-error / consecutive errors / last activity),
persisted to ``integration_health`` and kept current by a singleton."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

_STATES = {"ok", "degraded", "down", "disabled"}


@pytest.fixture(autouse=True)
def _env() -> Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing
    from bbz_core.integrations_host import providers as providers_mod

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "int-health-test-secret-at-least-32-bytes!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    # dwd's health() would poll DWD over the network (ADR-0026) — take it out
    os.environ["BBZ_WEATHER_INTEGRATION_ID"] = "none"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    settings_mod.get_settings.cache_clear()
    providers_mod.reset_provider_cache()
    yield
    os.environ.pop("BBZ_WEATHER_INTEGRATION_ID", None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    settings_mod.get_settings.cache_clear()
    providers_mod.reset_provider_cache()


async def _make_user(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    pw = hash_password("Wolke7-Bahnhof!x")
    s.add(LocalCredential(auth_identity_id=ident.id, password_hash=pw))
    if perms:
        role = Role(key=f"r-{username}", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    assert isinstance(db, AsyncSession)
    yield client, db


async def test_health_requires_diagnostics(env: tuple) -> None:
    client, s = env
    assert (await client.get("/api/v1/integrations/health")).status_code == 401
    await _make_user(s, "viewer", ["integrations.view"])  # not enough
    await _login(client, "viewer")
    assert (await client.get("/api/v1/integrations/health")).status_code == 403


async def test_lists_every_active_integration_with_a_normalised_state(env: tuple) -> None:
    client, s = env
    await _make_user(s, "ops", ["integrations.diagnostics"])
    await _login(client, "ops")

    body = (await client.get("/api/v1/integrations/health")).json()
    by_id = {i["integration_id"]: i for i in body["integrations"]}
    assert {"telephony_mock", "coda_video", "monitor_mock", "none"} <= set(by_id)
    for item in body["integrations"]:
        assert item["state"] in _STATES
        assert item["checked_at"] is not None
    assert by_id["telephony_mock"]["state"] == "ok"
    assert by_id["none"]["state"] == "down"  # BBZ_WEATHER_INTEGRATION_ID=none


async def test_a_failing_probe_increments_the_error_counter(
    env: tuple, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, s = env
    await _make_user(s, "ops2", ["integrations.diagnostics"])
    await _login(client, "ops2")

    from bbz_core.infra.repositories import integration_health as mod

    async def boom() -> object:
        raise RuntimeError("provider exploded")

    async def fake_provider() -> object:
        obj = type("P", (), {"health": boom})()
        return obj

    monkeypatch.setitem(mod._PROVIDER_FOR, "telephony", fake_provider)

    first = (await client.get("/api/v1/integrations/health")).json()["integrations"]
    tele = next(i for i in first if i["integration_id"] == "telephony_mock")
    assert tele["state"] == "down"
    assert tele["consecutive_errors"] == 1
    assert tele["last_error_at"] is not None

    second = (await client.get("/api/v1/integrations/health")).json()["integrations"]
    tele2 = next(i for i in second if i["integration_id"] == "telephony_mock")
    assert tele2["consecutive_errors"] == 2


async def test_last_activity_comes_from_the_provider_inbox(env: tuple) -> None:
    client, s = env
    await _make_user(s, "ops3", ["integrations.diagnostics"])
    await _login(client, "ops3")

    from bbz_core.infra.models.inbox import ProviderEventInbox

    s.add(
        ProviderEventInbox(
            provider="coda_video",
            dedupe_key=f"coda_video:{uuid.uuid4()}",
            raw_hash="h",
            normalized={},
        )
    )
    await s.commit()

    body = (await client.get("/api/v1/integrations/health")).json()
    coda = next(i for i in body["integrations"] if i["integration_id"] == "coda_video")
    assert coda["last_activity_at"] is not None


async def test_the_singleton_tick_refreshes_the_table(env: tuple) -> None:
    _client, s = env
    from bbz_core.infra.models.integration_health import IntegrationHealth
    from bbz_core.workers.registry import _integration_health_tick

    n = await _integration_health_tick()
    assert isinstance(n, int) and n >= 1

    await s.rollback()
    from sqlalchemy import select

    rows = (await s.execute(select(IntegrationHealth))).scalars().all()
    assert {r.integration_id for r in rows} >= {"telephony_mock", "coda_video", "monitor_mock"}
