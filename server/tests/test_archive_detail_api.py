"""GET /events/{id}/archive-detail — full, deterministically ordered history (E20-03).

The endpoint returns the same depth for an archived event as for an active one:
status history, notes, the domain-event log, every workflow instance with its
task results / decisions, audit references, and a reserved ``calls`` slot.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion

_ALL = [
    "events.create",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.postprocess",
    "events.archive",
    "events.view",
    "workflows.execute",
    "workflows.view",
]

_GRAPH: dict[str, Any] = {
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


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "archive-detail-api-secret-32-bytes-or-more!!"
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


def _cmd(command_id: uuid.UUID | None = None, *, version: int | None = None) -> dict[str, str]:
    h = {"X-Command-Id": str(command_id or uuid.uuid4())}
    if version is not None:
        h["X-Expected-Version"] = str(version)
    return h


async def _publish_template(s: AsyncSession, key: str) -> None:
    async with s.begin():
        tpl = WorkflowTemplate(key=key, name=key)
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="published", definition=_GRAPH
            )
        )


async def _run_event(client: httpx.AsyncClient, s: AsyncSession, *, with_workflow: bool) -> str:
    r = await client.post(
        "/api/v1/events",
        json={"title": "Rauchmelder Halle 3", "priority": "high", "description": "Q1"},
        headers=_cmd(),
    )
    eid = r.json()["id"]
    for verb, ver in (("accept", 1), ("acknowledge", 2), ("open", 3)):
        assert (
            await client.post(f"/api/v1/events/{eid}/{verb}", headers=_cmd(version=ver))
        ).status_code == 200
    assert (
        await client.post(f"/api/v1/events/{eid}/notes", json={"body": "vor Ort"}, headers=_cmd())
    ).status_code == 201
    if with_workflow:
        await _publish_template(s, "brand")
        st = await client.post(f"/api/v1/events/{eid}/workflow", json={"template_key": "brand"})
        assert st.status_code == 201, st.text
        cp = await client.post(
            f"/api/v1/events/{eid}/workflow/steps/m/complete", json={"result": {"ok": True}}
        )
        assert cp.status_code == 200, cp.text
    return eid


async def test_archive_detail_is_complete_and_deterministically_ordered(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl", _ALL)
    await _login(client, "sl")
    eid = await _run_event(client, s, with_workflow=True)
    assert (
        await client.post(
            f"/api/v1/events/{eid}/archive", json={"reason": "erledigt"}, headers=_cmd(version=4)
        )
    ).status_code == 200

    r = await client.get(f"/api/v1/events/{eid}/archive-detail")
    assert r.status_code == 200, r.text
    b = r.json()

    assert b["event"]["id"] == eid and b["event"]["status"] == "archived"
    assert [(h["from_status"], h["to_status"]) for h in b["event"]["status_history"]] == [
        (None, "new"),
        ("new", "accepted"),
        ("accepted", "acknowledged"),
        ("acknowledged", "opened"),
        ("opened", "archived"),
    ]
    assert [n["body"] for n in b["event"]["notes"]] == ["vor Ort"]

    seqs = [d["event_seq"] for d in b["domain_events"]]
    assert seqs == sorted(seqs)
    assert b["domain_events"][0]["event_type"] == "EVENT_CREATED"
    assert b["domain_events"][-1]["event_type"] == "EVENT_ARCHIVED"

    assert len(b["workflows"]) == 1
    wf = b["workflows"][0]
    assert wf["template_key"] == "brand" and wf["template_version"] == 1
    assert [t["node_key"] for t in wf["task_results"]] == ["m"]
    assert wf["task_results"][0]["result"] == {"ok": True}
    assert wf["decisions"] == []

    times = [a["occurred_at_utc"] for a in b["audit_refs"]]
    assert times == sorted(times)
    assert b["calls"] == []


async def test_archive_detail_depth_matches_active_event(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl2", _ALL)
    await _login(client, "sl2")
    eid = await _run_event(client, s, with_workflow=True)

    active = (await client.get(f"/api/v1/events/{eid}/archive-detail")).json()
    assert (
        await client.post(
            f"/api/v1/events/{eid}/archive", json={"reason": "x"}, headers=_cmd(version=4)
        )
    ).status_code == 200
    archived = (await client.get(f"/api/v1/events/{eid}/archive-detail")).json()

    def _depth(b: dict[str, Any]) -> dict[str, Any]:
        return {
            "notes": b["event"]["notes"],
            "workflows": b["workflows"],
            "domain_events": [d["event_type"] for d in b["domain_events"]],
        }

    a, z = _depth(active), _depth(archived)
    assert a["notes"] == z["notes"]
    assert a["workflows"] == z["workflows"]  # workflow history is untouched by archiving
    assert z["domain_events"] == [*a["domain_events"], "EVENT_ARCHIVED"]


async def test_archive_detail_unknown_event_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl3", _ALL)
    await _login(client, "sl3")
    assert (await client.get(f"/api/v1/events/{uuid.uuid4()}/archive-detail")).status_code == 404


async def test_archive_detail_requires_events_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl4", ["events.create"])
    await _login(client, "sl4")
    r = await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    eid = r.json()["id"]
    assert (await client.get(f"/api/v1/events/{eid}/archive-detail")).status_code == 403


async def test_archive_detail_without_workflow_has_empty_lists(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl5", _ALL)
    await _login(client, "sl5")
    eid = await _run_event(client, s, with_workflow=False)

    b = (await client.get(f"/api/v1/events/{eid}/archive-detail")).json()
    assert b["workflows"] == [] and b["calls"] == []
    assert b["domain_events"][-1]["event_type"] == "EVENT_NOTE_ADDED"
