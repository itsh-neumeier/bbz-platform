"""GET /events/{id}/export — full, reproducible bundle + optional PDF (E20-06)."""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion

_ALL = [
    "events.create",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.postprocess",
    "events.archive",
    "events.export",
    "events.view",
    "system.audit.view",
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
    "edges": [{"key": "a", "from": "e0", "to": "m"}, {"key": "b", "from": "m", "to": "e1"}],
}


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "export-bundle-secret-at-least-32-bytes-okay!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ.pop("BBZ_EXPORT_PDF_ENABLED", None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    os.environ.pop("BBZ_EXPORT_PDF_ENABLED", None)
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


def _enable_pdf() -> None:
    from bbz_core import settings as settings_mod

    os.environ["BBZ_EXPORT_PDF_ENABLED"] = "true"
    settings_mod.get_settings.cache_clear()


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


def _cmd(command_id: uuid.UUID | None = None, *, version: int | None = None) -> dict[str, str]:
    h = {"X-Command-Id": str(command_id or uuid.uuid4())}
    if version is not None:
        h["X-Expected-Version"] = str(version)
    return h


async def _publish(s: AsyncSession, key: str) -> None:
    async with s.begin():
        tpl = WorkflowTemplate(key=key, name=key)
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="published", definition=_GRAPH
            )
        )


async def _rich_event(client: httpx.AsyncClient, s: AsyncSession) -> str:
    r = await client.post(
        "/api/v1/events",
        json={"title": "Oberleitung", "priority": "high", "description": "Gleis 4"},
        headers=_cmd(),
    )
    eid = r.json()["id"]
    for verb, ver in (("accept", 1), ("acknowledge", 2), ("open", 3)):
        assert (
            await client.post(f"/api/v1/events/{eid}/{verb}", headers=_cmd(version=ver))
        ).status_code == 200
    assert (
        await client.post(f"/api/v1/events/{eid}/notes", json={"body": "Notiz A"}, headers=_cmd())
    ).status_code == 201
    await _publish(s, "wf")
    assert (
        await client.post(f"/api/v1/events/{eid}/workflow", json={"template_key": "wf"})
    ).status_code == 201
    assert (
        await client.post(
            f"/api/v1/events/{eid}/workflow/steps/m/complete", json={"result": {"done": 1}}
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/events/{eid}/archive", json={"reason": "fertig"}, headers=_cmd(version=4)
        )
    ).status_code == 200
    return eid


async def test_bundle_is_complete_and_deterministically_ordered(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl", _ALL)
    await _login(client, "sl")
    eid = await _rich_event(client, s)

    b = (await client.get(f"/api/v1/events/{eid}/export")).json()
    assert b["bundle_version"] == "1" and b["exported_at"]
    assert b["event"]["id"] == eid
    assert [n["body"] for n in b["event"]["notes"]] == ["Notiz A"]
    first_hist = b["event"]["status_history"][0]
    assert (first_hist["from_status"], first_hist["to_status"]) == (None, "new")

    seqs = [d["event_seq"] for d in b["domain_events"]]
    assert seqs == sorted(seqs)
    assert b["domain_events"][0]["event_type"] == "EVENT_CREATED"
    assert "EVENT_ARCHIVED" in [d["event_type"] for d in b["domain_events"]]

    assert len(b["workflows"]) == 1
    assert b["workflows"][0]["template_key"] == "wf"
    assert [t["node_key"] for t in b["workflows"][0]["task_results"]] == ["m"]

    times = [a["occurred_at_utc"] for a in b["audit_entries"]]
    assert times == sorted(times)
    actions = [a["action"] for a in b["audit_entries"]]
    assert "EVENT_ARCHIVED" in actions and "ACTION_STEP_COMPLETED" in actions
    # full entries, not just references
    archived = next(a for a in b["audit_entries"] if a["action"] == "EVENT_ARCHIVED")
    assert archived["after"]["status"] == "archived"
    assert b["calls"] == []


async def test_bundle_is_reproducible_across_calls(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl2", _ALL)
    await _login(client, "sl2")
    eid = await _rich_event(client, s)

    first = (await client.get(f"/api/v1/events/{eid}/export")).json()
    second = (await client.get(f"/api/v1/events/{eid}/export")).json()

    # everything except the export metadata and the export's own audit rows is identical
    def _stable(b: dict[str, Any]) -> str:
        b = dict(b)
        b.pop("exported_at")
        b["audit_entries"] = [a for a in b["audit_entries"] if a["action"] != "EVENT_EXPORTED"]
        return json.dumps(b, sort_keys=True)

    assert _stable(first) == _stable(second)


async def test_export_requires_export_and_audit_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "no_audit", ["events.create", "events.view", "events.export"])
    await _login(client, "no_audit")
    eid = (
        await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    ).json()["id"]
    assert (await client.get(f"/api/v1/events/{eid}/export")).status_code == 403

    await _make_user(s, "no_export", ["events.create", "events.view", "system.audit.view"])
    await _login(client, "no_export")
    assert (await client.get(f"/api/v1/events/{eid}/export")).status_code == 403


async def test_export_is_audited_with_the_format(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl3", _ALL)
    await _login(client, "sl3")
    eid = (
        await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    ).json()["id"]
    assert (await client.get(f"/api/v1/events/{eid}/export")).status_code == 200

    row = (
        await s.execute(
            select(AuditEvent).where(
                AuditEvent.action == "EVENT_EXPORTED", AuditEvent.target_id == eid
            )
        )
    ).scalar_one()
    assert row.after == {"format": "json"}


async def test_pdf_is_404_unless_enabled(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl4", _ALL)
    await _login(client, "sl4")
    eid = (
        await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    ).json()["id"]
    assert (await client.get(f"/api/v1/events/{eid}/export?format=pdf")).status_code == 404
    assert (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EVENT_EXPORTED")
        )
    ).scalar_one() == 0  # refused before the audit write


async def test_pdf_export_when_enabled(env: tuple) -> None:
    client, s = env
    _enable_pdf()
    await _make_user(s, "sl5", _ALL)
    await _login(client, "sl5")
    eid = (
        await client.post("/api/v1/events", json={"title": "x", "priority": "low"}, headers=_cmd())
    ).json()["id"]

    r = await client.get(f"/api/v1/events/{eid}/export?format=pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-1.")
    assert r.content.rstrip().endswith(b"%%EOF")
    assert eid.encode() in r.content  # the bundle text is embedded

    row = (
        await s.execute(select(AuditEvent).where(AuditEvent.action == "EVENT_EXPORTED"))
    ).scalar_one()
    assert row.after == {"format": "pdf"}


async def test_export_unknown_event_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl6", _ALL)
    await _login(client, "sl6")
    assert (await client.get(f"/api/v1/events/{uuid.uuid4()}/export")).status_code == 404
