"""Template-admin API: draft CRUD, simulation dry-run, diff (E05-13)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.outbox import ExternalActionOutbox

_MANAGE = ["workflows.view", "workflows.manage_templates"]

_ALARM: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {
            "key": "cam",
            "type": "function",
            "kind": "integration_action",
            "props": {"capability": "camera.point"},
        },
        {"key": "ack", "type": "function", "kind": "confirmation"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "cam"},
        {"key": "b", "from": "cam", "to": "ack"},
        {"key": "c", "from": "ack", "to": "e1"},
    ],
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "wfadmin-test-secret-at-least-32-bytes-okok!"
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
    if perms:
        role = Role(key=f"r-{username}", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            pid = (
                await s.execute(select(Permission.id).where(Permission.key == key))
            ).scalar_one_or_none()
            if pid is None:
                p = Permission(key=key, area=key.split(".")[0])
                s.add(p)
                await s.flush()
                pid = p.id
            s.add(RolePermission(role_id=role.id, permission_id=pid, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


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


async def _audit_count(s: AsyncSession, action: str) -> int:
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def _draft(client: httpx.AsyncClient, definition: dict[str, Any]) -> tuple[str, str]:
    tpl = await client.post(
        "/api/v1/workflow-templates", json={"key": f"k-{uuid.uuid4().hex[:8]}", "name": "T"}
    )
    assert tpl.status_code == 201, tpl.text
    ver = await client.post(
        f"/api/v1/workflow-templates/{tpl.json()['id']}/versions", json={"definition": definition}
    )
    assert ver.status_code == 201, ver.text
    return tpl.json()["id"], ver.json()["id"]


async def test_create_rename_and_read_a_template_are_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wa", _MANAGE)
    await _login(client, "wa")

    tid, vid = await _draft(client, _ALARM)
    assert await _audit_count(s, "WORKFLOW_TEMPLATE_CREATED") == 1
    assert await _audit_count(s, "WORKFLOW_TEMPLATE_UPDATED") == 1  # the draft version

    r = await client.patch(f"/api/v1/workflow-templates/{tid}", json={"name": "Neuer Name"})
    assert r.status_code == 200 and r.json()["name"] == "Neuer Name"
    assert await _audit_count(s, "WORKFLOW_TEMPLATE_UPDATED") == 2

    got = await client.get(f"/api/v1/workflow-templates/{tid}")
    assert got.status_code == 200
    assert [v["id"] for v in got.json()["versions"]] == [vid]


async def test_a_draft_version_can_be_deleted(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wa2", _MANAGE)
    await _login(client, "wa2")
    _, vid = await _draft(client, _ALARM)

    assert (await client.delete(f"/api/v1/workflow-template-versions/{vid}")).status_code == 204
    assert (await client.get(f"/api/v1/workflow-template-versions/{vid}")).status_code == 404
    # deleting it again -> 404 (already gone)
    assert (await client.delete(f"/api/v1/workflow-template-versions/{vid}")).status_code == 404


async def test_simulating_an_alarm_workflow_enqueues_nothing_real(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wa3", _MANAGE)
    await _login(client, "wa3")
    _, vid = await _draft(client, _ALARM)

    r = await client.post(
        f"/api/v1/workflow-template-versions/{vid}/simulate", json={"context": {}}
    )
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["status"] == "completed"
    assert [row["action_type"] for row in report["outbox_dry_run"]] == ["integration"]
    assert report["outbox_dry_run"][0]["payload"]["props"] == {"capability": "camera.point"}

    # the real outbox is untouched — no camera action was dispatched
    real = (await s.execute(select(func.count()).select_from(ExternalActionOutbox))).scalar_one()
    assert real == 0
    assert await _audit_count(s, "WORKFLOW_SIMULATED") == 1


async def test_diff_shows_changes_against_the_previous_version(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wa4", _MANAGE)
    await _login(client, "wa4")
    tid, _ = await _draft(client, _ALARM)

    v2def = {
        **_ALARM,
        "nodes": [*_ALARM["nodes"], {"key": "x", "type": "event"}],
        "edges": [*_ALARM["edges"], {"key": "z", "from": "ack", "to": "x"}],
    }
    v2 = await client.post(f"/api/v1/workflow-templates/{tid}/versions", json={"definition": v2def})
    d = await client.get(f"/api/v1/workflow-template-versions/{v2.json()['id']}/diff")
    assert d.status_code == 200
    assert d.json()["nodes_added"] == ["x"]
    assert d.json()["edges_added"] == ["z"]


async def test_manage_permission_is_required_for_writes(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["workflows.view"])
    await _make_user(s, "admin", _MANAGE)
    await _login(client, "admin")
    _, vid = await _draft(client, _ALARM)

    await _login(client, "viewer")
    assert (
        await client.post("/api/v1/workflow-templates", json={"key": "k", "name": "n"})
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/workflow-template-versions/{vid}/simulate", json={})
    ).status_code == 403
    # view-only endpoints still work
    assert (await client.get(f"/api/v1/workflow-template-versions/{vid}/diff")).status_code == 200
