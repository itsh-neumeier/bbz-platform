"""Operator instance API: view, complete step, decide branch (E05-12)."""

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
from bbz_core.infra.models.events import Event
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion

_EXEC = ["workflows.view", "workflows.execute"]


def _cond(field: str, value: str) -> dict[str, Any]:
    return {"op": "eq", "args": [{"field": field}, value]}


_AND: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "as", "type": "connector", "connector": "and", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual", "label": "Zufahrt sichern"},
        {"key": "f2", "type": "function", "kind": "documentation"},
        {"key": "aj", "type": "connector", "connector": "and", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "as"},
        {"key": "b", "from": "as", "to": "f1"},
        {"key": "c", "from": "as", "to": "f2"},
        {"key": "d", "from": "f1", "to": "aj"},
        {"key": "e", "from": "f2", "to": "aj"},
        {"key": "f", "from": "aj", "to": "e1"},
    ],
}

_XOR: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "manual"},
        {"key": "xj", "type": "connector", "connector": "xor", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "xs"},
        {"key": "b", "from": "xs", "to": "f1", "condition": _cond("status", "x")},
        {"key": "c", "from": "xs", "to": "f2", "condition": _cond("status", "y")},
        {"key": "d", "from": "f1", "to": "xj"},
        {"key": "e", "from": "f2", "to": "xj"},
        {"key": "f", "from": "xj", "to": "e1"},
    ],
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "wfinst-test-secret-at-least-32-bytes-okok!!"
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


async def _start(
    s: AsyncSession, definition: dict[str, Any], *, priority: str = "high"
) -> tuple[uuid.UUID, str]:
    """Publish a template + event; return (event_id, template_key)."""
    async with s.begin():
        ev = Event(title="Lage", priority=priority)
        tpl = WorkflowTemplate(key=f"wf-{uuid.uuid4().hex[:6]}", name="wf")
        s.add_all([ev, tpl])
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="published", definition=definition
            )
        )
        return ev.id, tpl.key


async def _audit_count(s: AsyncSession, action: str) -> int:
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_view_mirrors_the_token_state_through_an_and_graph(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _EXEC)
    await _login(client, "op")
    event_id, key = await _start(s, _AND)
    await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": key})

    view = (await client.get(f"/api/v1/events/{event_id}/workflow")).json()
    assert view["status"] == "running"
    assert view["progress"] == {"done": 0, "total": 2}
    by_key = {st["node_key"]: st for st in view["steps"]}
    assert by_key["f1"]["state"] == "active" and by_key["f1"]["label"] == "Zufahrt sichern"
    assert by_key["f2"]["state"] == "active"
    assert any(a["action"] == "WORKFLOW_INSTANCE_STARTED" for a in view["audit"])

    r = await client.post(
        f"/api/v1/events/{event_id}/workflow/steps/f1/complete", json={"result": {"ok": True}}
    )
    assert r.status_code == 200
    mid = r.json()
    assert mid["progress"] == {"done": 1, "total": 2}
    assert {st["node_key"]: st["state"] for st in mid["steps"]}["f1"] == "done"
    assert mid["status"] == "running"

    end = (
        await client.post(f"/api/v1/events/{event_id}/workflow/steps/f2/complete", json={})
    ).json()
    assert end["status"] == "completed"
    assert end["progress"] == {"done": 2, "total": 2}
    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 2


async def test_xor_graph_is_worked_via_an_operator_decision(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _EXEC)
    await _login(client, "op2")
    event_id, key = await _start(s, _XOR, priority="low")  # no branch condition matches
    await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": key})

    view = (await client.get(f"/api/v1/events/{event_id}/workflow")).json()
    assert len(view["pending_decisions"]) == 1
    pd = view["pending_decisions"][0]
    assert pd["connector_node_key"] == "xs" and pd["connector_type"] == "xor"
    assert {o["edge_key"] for o in pd["options"]} == {"b", "c"}

    after = (
        await client.post(
            f"/api/v1/events/{event_id}/workflow/decisions/xs", json={"chosen": ["c"]}
        )
    ).json()
    assert after["pending_decisions"] == []
    assert {st["node_key"]: st["state"] for st in after["steps"]}["f2"] == "active"
    assert after["decisions"][0]["chosen_branches"] == ["c"]
    assert after["decisions"][0]["auto"] is False

    done = (
        await client.post(f"/api/v1/events/{event_id}/workflow/steps/f2/complete", json={})
    ).json()
    assert done["status"] == "completed"
    assert await _audit_count(s, "WORKFLOW_DECISION_MADE") == 1


async def test_completing_a_step_out_of_order_is_a_conflict(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", _EXEC)
    await _login(client, "op3")
    event_id, key = await _start(s, _AND)
    await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": key})

    r = await client.post(f"/api/v1/events/{event_id}/workflow/steps/aj/complete", json={})
    assert r.status_code == 409


async def test_step_completion_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4", _EXEC)
    await _login(client, "op4")
    event_id, key = await _start(s, _AND)
    await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": key})

    a = await client.post(f"/api/v1/events/{event_id}/workflow/steps/f1/complete", json={})
    b = await client.post(f"/api/v1/events/{event_id}/workflow/steps/f1/complete", json={})
    assert a.status_code == 200 and b.status_code == 200
    assert await _audit_count(s, "ACTION_STEP_COMPLETED") == 1


async def test_view_needs_view_permission_and_write_needs_execute(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["workflows.view"])
    await _make_user(s, "nobody", [])
    event_id, key = await _start(s, _AND)
    await _make_user(s, "starter", _EXEC)
    await _login(client, "starter")
    await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": key})

    await _login(client, "nobody")
    assert (await client.get(f"/api/v1/events/{event_id}/workflow")).status_code == 403

    await _login(client, "viewer")
    assert (await client.get(f"/api/v1/events/{event_id}/workflow")).status_code == 200
    assert (
        await client.post(f"/api/v1/events/{event_id}/workflow/steps/f1/complete", json={})
    ).status_code == 403


async def test_view_without_an_instance_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5", _EXEC)
    await _login(client, "op5")
    async with s.begin():
        ev = Event(title="x", priority="low")
        s.add(ev)
        await s.flush()
        event_id = ev.id
    assert (await client.get(f"/api/v1/events/{event_id}/workflow")).status_code == 404
