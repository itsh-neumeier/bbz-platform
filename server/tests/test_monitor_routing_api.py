"""Monitor routing API (roadmap E19-04): GET/PUT /monitor/routes +
POST /monitor/routes/reset-standard against monitor_mock — idempotent, audited,
the lower-left BBZ-OS rule enforced server-side."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.monitor import INPUTS, OUTPUTS
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.monitor import MonitorInput, MonitorOutput, MonitorRoute


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "monitor-api-test-secret-at-least-32-bytes!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


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
    s.add(
        LocalCredential(auth_identity_id=ident.id, password_hash=hash_password("Wolke7-Bahnhof!x"))
    )
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


async def _seed_catalog(s: AsyncSession, *, routes: dict[str, str] | None = None) -> None:
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
        await s.flush()
        if routes:
            in_ids = {r.key: r.id for r in (await s.execute(select(MonitorInput))).scalars()}
            out_ids = {r.key: r.id for r in (await s.execute(select(MonitorOutput))).scalars()}
            import datetime as _dt

            for ok, ik in routes.items():
                s.add(
                    MonitorRoute(
                        output_id=out_ids[ok],
                        input_id=in_ids[ik],
                        set_at=_dt.datetime.now(_dt.UTC),
                    )
                )


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    yield client, s


async def _login(client: httpx.AsyncClient, username: str) -> None:
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


def _cmd() -> dict[str, str]:
    return {"X-Command-Id": str(uuid.uuid4())}


async def _audit_count(s: AsyncSession) -> int:
    await s.rollback()
    return (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "MONITOR_ROUTE_CHANGED")
        )
    ).scalar_one()


async def test_get_routes_returns_the_catalog_and_the_fixed_flag(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["monitor.view"])
    await _seed_catalog(s, routes={"workplace1": "bku1", "workplace4": "bbz-os"})
    await _login(client, "op")

    body = (await client.get("/api/v1/monitor/routes")).json()
    assert {i["key"] for i in body["inputs"]} == {i.key for i in INPUTS}
    assert len(body["outputs"]) == 7
    fixed = {o["key"] for o in body["outputs"] if o["is_fixed"]}
    assert fixed == {"workplace4"}
    routed = {r["output_key"]: r["input_key"] for r in body["routes"]}
    assert routed["workplace1"] == "bku1" and routed["workplace4"] == "bbz-os"
    assert routed["large-display"] is None  # unrouted


async def test_put_routes_sets_a_route_and_audits_it(env: tuple) -> None:
    client, s = env
    from bbz_core.integrations_host.providers import active_monitor_provider

    await _make_user(s, "op", ["monitor.view", "monitor.route"])
    await _seed_catalog(s, routes={"workplace2": "bku2"})
    await _login(client, "op")

    r = await client.put(
        "/api/v1/monitor/routes",
        json={"assignments": {"workplace2": "coda1"}},
        headers=_cmd(),
    )
    assert r.status_code == 200, r.text
    routed = {x["output_key"]: x["input_key"] for x in r.json()["routes"]}
    assert routed["workplace2"] == "coda1"

    # persisted + reflected on the provider + audited once
    await s.rollback()
    row = (await s.execute(select(MonitorRoute))).scalar_one()
    assert row.set_by is not None
    provider = await active_monitor_provider()
    assert {x["output_id"]: x["input_id"] for x in await provider.get_routes()}[
        "workplace2"
    ] == "coda1"
    assert await _audit_count(s) == 1
    audit = (await s.execute(select(AuditEvent))).scalars().all()[-1]
    assert audit.before == {"input": "bku2"} and audit.after == {"input": "coda1"}


async def test_reassigning_the_lower_left_output_is_refused(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["monitor.route"])
    await _seed_catalog(s, routes={"workplace4": "bbz-os"})
    await _login(client, "op")

    r = await client.put(
        "/api/v1/monitor/routes",
        json={"assignments": {"workplace4": "bku1"}},
        headers=_cmd(),
    )
    assert r.status_code == 422
    await s.rollback()
    assert (await s.execute(select(MonitorRoute))).scalar_one().input_id is not None
    assert await _audit_count(s) == 0


async def test_a_repeated_command_id_does_not_route_or_audit_twice(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["monitor.route", "monitor.view"])
    await _seed_catalog(s, routes={"workplace3": "bku3"})
    await _login(client, "op")

    headers = _cmd()
    body = {"assignments": {"workplace3": "coda2"}}
    r1 = await client.put("/api/v1/monitor/routes", json=body, headers=headers)
    r2 = await client.put("/api/v1/monitor/routes", json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200
    assert await _audit_count(s) == 1  # the replay applied nothing


async def test_reset_to_standard_restores_the_layout_and_keeps_the_rule(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["monitor.reset_standard", "monitor.view"])
    await _seed_catalog(s, routes={"workplace1": "coda1", "workplace4": "bbz-os"})
    await _login(client, "op")

    r = await client.post("/api/v1/monitor/routes/reset-standard", headers=_cmd())
    assert r.status_code == 200, r.text
    routed = {x["output_key"]: x["input_key"] for x in r.json()["routes"]}
    from bbz_core.domain.monitor import standard_layout

    assert routed == standard_layout()
    assert routed["workplace4"] == "bbz-os"


async def test_rights_are_enforced(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["monitor.view"])
    await _seed_catalog(s)
    await _login(client, "viewer")

    assert (
        await client.put(
            "/api/v1/monitor/routes",
            json={"assignments": {"workplace1": "bku1"}},
            headers=_cmd(),
        )
    ).status_code == 403
    assert (
        await client.post("/api/v1/monitor/routes/reset-standard", headers=_cmd())
    ).status_code == 403


async def test_an_unknown_output_key_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", ["monitor.route"])
    await _seed_catalog(s)
    await _login(client, "op")

    r = await client.put(
        "/api/v1/monitor/routes",
        json={"assignments": {"workplace99": "bku1"}},
        headers=_cmd(),
    )
    assert r.status_code == 422


async def test_no_active_provider_is_a_503(env: tuple) -> None:
    client, s = env
    os.environ["BBZ_MONITOR_INTEGRATION_ID"] = "none"
    from bbz_core import settings as settings_mod

    settings_mod.get_settings.cache_clear()
    try:
        await _make_user(s, "op", ["monitor.route"])
        await _seed_catalog(s, routes={"workplace2": "bku2"})
        await _login(client, "op")
        r = await client.put(
            "/api/v1/monitor/routes",
            json={"assignments": {"workplace2": "coda1"}},
            headers=_cmd(),
        )
        assert r.status_code == 503
    finally:
        os.environ.pop("BBZ_MONITOR_INTEGRATION_ID", None)
        settings_mod.get_settings.cache_clear()
