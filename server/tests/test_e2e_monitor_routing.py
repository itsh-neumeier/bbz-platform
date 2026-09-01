"""End-to-end: monitor routing — set a route, reset to standard, the fixed
lower-left rule, and save + apply a layout profile (roadmap E19-10,
MASTER_PROMPT §9).

The browser layer (Playwright over Compose against ``monitor_mock``) is
scaffolded in ``apps/web/e2e/monitor-routing.spec.ts`` and lands with the E19-08
dialog UI; this walks the same four scenarios at the API level as one continuous
session and asserts the audit trail and that the mock reflects every change.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.monitor import INPUTS, OUTPUTS, standard_layout
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.monitor import MonitorInput, MonitorOutput, MonitorRoute


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "monitor-e2e-test-secret-at-least-32-bytes"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


async def _make_operator(s: AsyncSession) -> None:
    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name="Sichtleiter")
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject="chef")
    s.add(ident)
    await s.flush()
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
    role = Role(key="r-chef", name="R")
    s.add(role)
    await s.flush()
    for key in (
        "monitor.view",
        "monitor.route",
        "monitor.reset_standard",
        "monitor.manage_profiles",
    ):
        p = Permission(key=key, area="monitor")
        s.add(p)
        await s.flush()
        s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
    s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()


async def _seed_catalog(s: AsyncSession) -> None:
    await s.rollback()
    async with s.begin():
        for i in INPUTS:
            s.add(MonitorInput(key=i.key, label=i.label, sort_order=i.sort_order))
        for o in OUTPUTS:
            s.add(
                MonitorOutput(
                    key=o.key,
                    label=o.label,
                    grid_row=o.grid_row,
                    grid_col=o.grid_col,
                    is_large_display=o.is_large_display,
                    sort_order=o.sort_order,
                )
            )


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    await _make_operator(s)
    await _seed_catalog(s)
    r = await client.post(
        "/api/v1/auth/login", json={"username": "chef", "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text
    yield client, s


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def _monitor_audits(s: AsyncSession) -> list[str]:
    await s.rollback()
    return [
        a
        for (a,) in (
            await s.execute(select(AuditEvent.action).order_by(AuditEvent.occurred_at_utc))
        ).all()
        if a.startswith("MONITOR_")
    ]


async def test_the_four_monitor_scenarios_end_to_end(env: tuple) -> None:
    client, s = env
    from bbz_core.integrations_host.providers import active_monitor_provider

    async def mock_routes() -> dict[str, str]:
        provider = await active_monitor_provider()
        return {x["output_id"]: x["input_id"] for x in await provider.get_routes()}

    # 1. set a route — the mock reflects it and it is audited
    r = await client.put(
        "/api/v1/monitor/routes",
        json={"assignments": {"workplace3": "coda1"}},
        headers=_cmd(),
    )
    assert r.status_code == 200
    assert {x["output_key"]: x["input_key"] for x in r.json()["routes"]}["workplace3"] == "coda1"
    assert (await mock_routes())["workplace3"] == "coda1"
    assert await _monitor_audits(s) == ["MONITOR_ROUTE_CHANGED"]

    # 2. the fixed lower-left rule — a reassignment is refused, nothing changes
    r = await client.put(
        "/api/v1/monitor/routes",
        json={"assignments": {"workplace4": "bku1"}},
        headers=_cmd(),
    )
    assert r.status_code == 422
    assert await _monitor_audits(s) == ["MONITOR_ROUTE_CHANGED"]  # unchanged

    # 3. save a layout profile and apply it — routes match, standard rule holds
    layout = standard_layout()
    layout["workplace6"] = "bku2"
    pid = (
        await client.post(
            "/api/v1/monitor/profiles",
            json={"name": "Nachtdienst", "scope": "user", "layout": layout},
        )
    ).json()["id"]
    r = await client.post(f"/api/v1/monitor/profiles/{pid}/apply", headers=_cmd())
    assert r.status_code == 200
    assert {x["output_key"]: x["input_key"] for x in r.json()["routes"]} == layout
    assert await mock_routes() == layout
    assert (await mock_routes())["workplace4"] == "bbz-os"
    assert "MONITOR_PROFILE_APPLIED" in await _monitor_audits(s)

    # 4. reset to standard — everything returns to the documented default
    r = await client.post("/api/v1/monitor/routes/reset-standard", headers=_cmd())
    assert r.status_code == 200
    assert {x["output_key"]: x["input_key"] for x in r.json()["routes"]} == standard_layout()
    assert await mock_routes() == standard_layout()

    # the whole session left an audit trail; every applied route row is on the DB
    audits = await _monitor_audits(s)
    assert audits[0] == "MONITOR_ROUTE_CHANGED" and "MONITOR_PROFILE_APPLIED" in audits
    await s.rollback()
    assert (await s.execute(select(MonitorRoute))).scalars().all()  # persisted
