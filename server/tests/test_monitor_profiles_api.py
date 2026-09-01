"""Monitor layout profiles API (roadmap E19-05): CRUD + apply, scope visibility,
the fixed BBZ-OS rule on apply, MONITOR_PROFILE_APPLIED audit."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.monitor import INPUTS, OUTPUTS, standard_layout
from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.monitor import MonitorInput, MonitorOutput, MonitorRoute


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "monitor-prof-test-secret-at-least-32-byte"
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
        p = (await s.execute(select(Permission).where(Permission.key == key))).scalar_one_or_none()
        if p is None:
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
            import datetime as _dt

            in_ids = {r.key: r.id for r in (await s.execute(select(MonitorInput))).scalars()}
            out_ids = {r.key: r.id for r in (await s.execute(select(MonitorOutput))).scalars()}
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


_MANAGE = ["monitor.view", "monitor.manage_profiles", "monitor.route"]


async def test_create_a_user_profile_and_list_it(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _MANAGE)
    await _seed_catalog(s)
    await _login(client, "op")

    layout = standard_layout()
    r = await client.post(
        "/api/v1/monitor/profiles",
        json={"name": "Frühdienst", "scope": "user", "layout": layout},
    )
    assert r.status_code == 201, r.text
    assert r.json()["scope"] == "user" and r.json()["layout"] == layout

    listed = (await client.get("/api/v1/monitor/profiles")).json()["profiles"]
    assert [p["name"] for p in listed] == ["Frühdienst"]


async def test_an_invalid_layout_is_refused(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _MANAGE)
    await _seed_catalog(s)
    await _login(client, "op")

    bad = standard_layout()
    bad["workplace4"] = "bku1"  # violates the fixed lower-left rule
    r = await client.post(
        "/api/v1/monitor/profiles", json={"name": "x", "scope": "user", "layout": bad}
    )
    assert r.status_code == 422

    incomplete = standard_layout()
    incomplete.pop("large-display")
    r = await client.post(
        "/api/v1/monitor/profiles",
        json={"name": "y", "scope": "user", "layout": incomplete},
    )
    assert r.status_code == 422


async def test_a_workplace_profile_needs_a_workplace_id(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _MANAGE)
    await _seed_catalog(s)
    await _login(client, "op")

    r = await client.post(
        "/api/v1/monitor/profiles",
        json={"name": "AP-Standard", "scope": "workplace", "layout": standard_layout()},
    )
    assert r.status_code == 422

    wp = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/monitor/profiles",
        json={
            "name": "AP-Standard",
            "scope": "workplace",
            "layout": standard_layout(),
            "workplace_id": wp,
        },
    )
    assert r.status_code == 201
    # visible only with the matching workplace_id
    assert (await client.get("/api/v1/monitor/profiles")).json()["profiles"] == []
    seen = (await client.get(f"/api/v1/monitor/profiles?workplace_id={wp}")).json()["profiles"]
    assert [p["name"] for p in seen] == ["AP-Standard"]


async def test_user_profiles_are_private(env: tuple) -> None:
    client, s = env
    a = await _make_user(s, "alice", _MANAGE)
    await _make_user(s, "bob", _MANAGE)
    await _seed_catalog(s)

    await _login(client, "alice")
    await client.post(
        "/api/v1/monitor/profiles",
        json={"name": "alice-only", "scope": "user", "layout": standard_layout()},
    )
    await _login(client, "bob")
    assert (await client.get("/api/v1/monitor/profiles")).json()["profiles"] == []
    assert a  # keep the id referenced


async def test_name_is_unique_within_scope(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _MANAGE)
    await _seed_catalog(s)
    await _login(client, "op")

    body = {"name": "dup", "scope": "user", "layout": standard_layout()}
    assert (await client.post("/api/v1/monitor/profiles", json=body)).status_code == 201
    assert (await client.post("/api/v1/monitor/profiles", json=body)).status_code == 409


async def test_apply_a_profile_routes_and_audits(env: tuple) -> None:
    client, s = env
    from bbz_core.integrations_host.providers import active_monitor_provider

    await _make_user(s, "op", _MANAGE)
    await _seed_catalog(s, routes={"workplace1": "bku4", "workplace4": "bbz-os"})
    await _login(client, "op")

    pid = (
        await client.post(
            "/api/v1/monitor/profiles",
            json={"name": "P", "scope": "user", "layout": standard_layout()},
        )
    ).json()["id"]

    r = await client.post(f"/api/v1/monitor/profiles/{pid}/apply", headers=_cmd())
    assert r.status_code == 200, r.text
    routed = {x["output_key"]: x["input_key"] for x in r.json()["routes"]}
    assert routed == standard_layout()
    assert routed["workplace4"] == "bbz-os"

    provider = await active_monitor_provider()
    assert {x["output_id"]: x["input_id"] for x in await provider.get_routes()}[
        "workplace1"
    ] == "bku1"

    await s.rollback()
    actions = [
        a for (a,) in (await s.execute(select(AuditEvent.action))).all() if a.startswith("MONITOR_")
    ]
    assert "MONITOR_PROFILE_APPLIED" in actions
    assert actions.count("MONITOR_ROUTE_CHANGED") >= 1
    # the applied routes carry the profile id
    row = (
        await s.execute(
            select(MonitorRoute).join(MonitorOutput).where(MonitorOutput.key == "workplace1")
        )
    ).scalar_one()
    assert str(row.profile_id) == pid


async def test_apply_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _MANAGE)
    await _seed_catalog(s, routes={"workplace1": "bku4"})
    await _login(client, "op")

    pid = (
        await client.post(
            "/api/v1/monitor/profiles",
            json={"name": "P", "scope": "user", "layout": standard_layout()},
        )
    ).json()["id"]
    h = _cmd()
    r1 = await client.post(f"/api/v1/monitor/profiles/{pid}/apply", headers=h)
    r2 = await client.post(f"/api/v1/monitor/profiles/{pid}/apply", headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    await s.rollback()
    n = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "MONITOR_PROFILE_APPLIED")
        )
    ).scalar_one()
    assert n == 1


async def test_update_and_delete(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _MANAGE)
    await _seed_catalog(s)
    await _login(client, "op")

    pid = (
        await client.post(
            "/api/v1/monitor/profiles",
            json={"name": "P", "scope": "user", "layout": standard_layout()},
        )
    ).json()["id"]
    r = await client.put(f"/api/v1/monitor/profiles/{pid}", json={"name": "P2"})
    assert r.status_code == 200 and r.json()["name"] == "P2"
    assert (await client.delete(f"/api/v1/monitor/profiles/{pid}")).status_code == 204
    assert (await client.get("/api/v1/monitor/profiles")).json()["profiles"] == []


async def test_rights(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["monitor.view"])
    await _seed_catalog(s)
    await _login(client, "viewer")
    r = await client.post(
        "/api/v1/monitor/profiles",
        json={"name": "x", "scope": "user", "layout": standard_layout()},
    )
    assert r.status_code == 403
