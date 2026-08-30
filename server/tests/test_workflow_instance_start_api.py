"""Start a workflow instance from an event, pinned to a PUBLISHED version (E05-11)."""

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

_G1: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "m", "type": "function", "kind": "manual"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "m"},
        {"key": "b", "from": "m", "to": "e1"},
    ],
}
# v2 is a single end event — visibly different from v1
_G2: dict[str, Any] = {"start": "e0", "nodes": [{"key": "e0", "type": "event"}], "edges": []}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "wfstart-test-secret-at-least-32-bytes-okok!"
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


async def _event(s: AsyncSession) -> uuid.UUID:
    async with s.begin():
        ev = Event(title="Rauchmelder", priority="high")
        s.add(ev)
        await s.flush()
        return ev.id


async def _template(s: AsyncSession, key: str, *versions: dict[str, Any]) -> None:
    async with s.begin():
        tpl = WorkflowTemplate(key=key, name=key)
        s.add(tpl)
        await s.flush()
        for i, definition in enumerate(versions, start=1):
            s.add(
                WorkflowTemplateVersion(
                    template_id=tpl.id,
                    version_no=i,
                    lifecycle="published",
                    definition=definition,
                )
            )


async def _audit_count(s: AsyncSession, action: str) -> int:
    return (
        await s.execute(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == action)
        )
    ).scalar_one()


async def test_start_pins_the_instance_to_the_current_published_version(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _EXEC)
    await _login(client, "op")
    event_id = await _event(s)
    await _template(s, "ablauf", _G1)

    r = await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": "ablauf"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "running"  # parked on the manual step
    assert body["event_id"] == str(event_id)
    assert await _audit_count(s, "WORKFLOW_INSTANCE_STARTED") == 1

    pinned = (
        await s.execute(
            select(WorkflowTemplateVersion.version_no).where(
                WorkflowTemplateVersion.id == uuid.UUID(body["template_version_id"])
            )
        )
    ).scalar_one()
    assert pinned == 1


async def test_a_later_publish_does_not_touch_a_running_instance(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _EXEC)
    await _login(client, "op2")
    event_id = await _event(s)
    await _template(s, "ab2", _G1)  # only v1 published

    started = (
        await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": "ab2"})
    ).json()
    v1_id = started["template_version_id"]
    instance_id = uuid.UUID(started["instance_id"])

    # publish v2 with a different graph
    async with s.begin():
        tpl_id = (
            await s.execute(select(WorkflowTemplate.id).where(WorkflowTemplate.key == "ab2"))
        ).scalar_one()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl_id, version_no=2, lifecycle="published", definition=_G2
            )
        )

    # the running instance is still pinned to v1 and still on v1's manual step
    from bbz_core.infra.models.workflow_runtime import WorkflowInstance, WorkflowToken

    inst = await s.get(WorkflowInstance, instance_id)
    assert inst is not None and inst.template_version_id == uuid.UUID(v1_id)
    assert inst.status == "running"
    parked = (
        (
            await s.execute(
                select(WorkflowToken.node_key).where(
                    WorkflowToken.instance_id == instance_id,
                    WorkflowToken.state == "waiting",
                )
            )
        )
        .scalars()
        .all()
    )
    assert parked == ["m"]  # v1's node — v2 has no such node
    await s.rollback()

    # a fresh start now pins to v2
    again = (
        await client.post(
            f"/api/v1/events/{await _event(s)}/workflow", json={"template_key": "ab2"}
        )
    ).json()
    v2_no = (
        await s.execute(
            select(WorkflowTemplateVersion.version_no).where(
                WorkflowTemplateVersion.id == uuid.UUID(again["template_version_id"])
            )
        )
    ).scalar_one()
    assert v2_no == 2


async def test_start_is_idempotent_for_the_same_event_and_version(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", _EXEC)
    await _login(client, "op3")
    event_id = await _event(s)
    await _template(s, "ab3", _G1)

    first = await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": "ab3"})
    second = await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": "ab3"})
    assert first.json()["instance_id"] == second.json()["instance_id"]
    assert await _audit_count(s, "WORKFLOW_INSTANCE_STARTED") == 1


async def test_start_without_a_published_version_is_rejected(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4", _EXEC)
    await _login(client, "op4")
    event_id = await _event(s)
    async with s.begin():
        tpl = WorkflowTemplate(key="draftonly", name="d")
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="draft", definition=_G1
            )
        )

    r = await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": "draftonly"})
    assert r.status_code == 409


async def test_unknown_template_and_event_give_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5", _EXEC)
    await _login(client, "op5")
    event_id = await _event(s)
    await _template(s, "ab5", _G1)

    assert (
        await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": "nope"})
    ).status_code == 404
    assert (
        await client.post(f"/api/v1/events/{uuid.uuid4()}/workflow", json={"template_key": "ab5"})
    ).status_code == 404


async def test_execute_permission_is_required(env: tuple) -> None:
    client, s = env
    await _make_user(s, "viewer", ["workflows.view"])
    await _login(client, "viewer")
    event_id = await _event(s)
    await _template(s, "ab6", _G1)
    r = await client.post(f"/api/v1/events/{event_id}/workflow", json={"template_key": "ab6"})
    assert r.status_code == 403
