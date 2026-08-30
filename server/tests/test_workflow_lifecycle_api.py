"""Workflow template-version lifecycle API: transitions, immutability (E05-07)."""

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

_MANAGE = ["workflows.view", "workflows.manage_templates"]

_VALID_GRAPH: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "documentation"},
        {"key": "xj", "type": "connector", "connector": "xor", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "xs"},
        {
            "key": "b",
            "from": "xs",
            "to": "f1",
            "condition": {"op": "eq", "args": [{"field": "event_priority"}, "critical"]},
        },
        {"key": "c", "from": "xs", "to": "f2"},
        {"key": "d", "from": "f1", "to": "xj"},
        {"key": "e", "from": "f2", "to": "xj"},
        {"key": "f", "from": "xj", "to": "e1"},
    ],
}
_BROKEN_GRAPH: dict[str, Any] = {
    "start": "e0",
    "nodes": [{"key": "e0", "type": "event"}, {"key": "orphan", "type": "event"}],
    "edges": [],
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "wf-test-secret-at-least-32-bytes-long-okok!!"
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
            p = Permission(key=key, area=key.split(".")[0])
            s.add(p)
            await s.flush()
            s.add(RolePermission(role_id=role.id, permission_id=p.id, scope="global"))
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


async def _new_version(client: httpx.AsyncClient, graph: dict[str, Any]) -> str:
    tpl = await client.post(
        "/api/v1/workflow-templates", json={"key": f"k-{uuid.uuid4().hex[:8]}", "name": "T"}
    )
    assert tpl.status_code == 201, tpl.text
    ver = await client.post(
        f"/api/v1/workflow-templates/{tpl.json()['id']}/versions", json={"definition": graph}
    )
    assert ver.status_code == 201, ver.text
    return ver.json()["id"]


async def test_full_lifecycle_validate_publish_deprecate(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wfadmin", _MANAGE)
    await _login(client, "wfadmin")
    vid = await _new_version(client, _VALID_GRAPH)

    val = await client.post(f"/api/v1/workflow-template-versions/{vid}/validate")
    assert val.status_code == 200 and val.json()["valid"] is True
    assert val.json()["lifecycle"] == "validated"

    pub = await client.post(
        f"/api/v1/workflow-template-versions/{vid}/publish",
        json={"changelog": "erste Fassung"},
    )
    assert pub.status_code == 200 and pub.json()["lifecycle"] == "published"

    dep = await client.post(f"/api/v1/workflow-template-versions/{vid}/deprecate")
    assert dep.status_code == 200 and dep.json()["lifecycle"] == "deprecated"

    for action in (
        "WORKFLOW_TEMPLATE_VALIDATED",
        "WORKFLOW_TEMPLATE_PUBLISHED",
        "WORKFLOW_TEMPLATE_DEPRECATED",
    ):
        n = (
            await s.execute(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
            )
        ).scalar_one()
        assert n == 1, action


async def test_publish_requires_prior_validation(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wf2", _MANAGE)
    await _login(client, "wf2")
    vid = await _new_version(client, _VALID_GRAPH)
    r = await client.post(
        f"/api/v1/workflow-template-versions/{vid}/publish", json={"changelog": "x"}
    )
    assert r.status_code == 409


async def test_publish_needs_a_changelog(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wf3", _MANAGE)
    await _login(client, "wf3")
    vid = await _new_version(client, _VALID_GRAPH)
    await client.post(f"/api/v1/workflow-template-versions/{vid}/validate")
    r = await client.post(
        f"/api/v1/workflow-template-versions/{vid}/publish", json={"changelog": ""}
    )
    assert r.status_code == 422


async def test_invalid_graph_reports_issues_and_stays_draft(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wf4", _MANAGE)
    await _login(client, "wf4")
    vid = await _new_version(client, _BROKEN_GRAPH)
    r = await client.post(f"/api/v1/workflow-template-versions/{vid}/validate")
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False and body["lifecycle"] == "draft"
    assert {i["code"] for i in body["issues"]} >= {"orphan"}


async def test_published_version_cannot_be_edited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "wf5", _MANAGE)
    await _login(client, "wf5")
    vid = await _new_version(client, _VALID_GRAPH)
    await client.post(f"/api/v1/workflow-template-versions/{vid}/validate")
    await client.post(f"/api/v1/workflow-template-versions/{vid}/publish", json={"changelog": "v1"})
    r = await client.patch(
        f"/api/v1/workflow-template-versions/{vid}", json={"definition": _VALID_GRAPH}
    )
    assert r.status_code == 409


async def test_manage_permission_is_required(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["workflows.view"])
    await _login(client, "viewer")
    r = await client.post("/api/v1/workflow-templates", json={"key": "k", "name": "n"})
    assert r.status_code == 403
    assert (await client.get("/api/v1/workflow-templates")).status_code == 200
