"""End-to-end: archive → detail → post-processing note → export → reactivation.

Roadmap E20-08. MASTER_PROMPT section 24 (steps 8-10) / 13.6. The browser layer
(Playwright over Compose) is scaffolded in ``apps/web/e2e/archive-lifecycle.spec.ts``
and lands with the E07-11 / E07-12 UI; this walks the same flow at the API level
and asserts the audit trail and the "nothing is hard-deleted" guarantee.
"""

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
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import EventNote
from bbz_core.infra.models.workflow import WorkflowTemplate, WorkflowTemplateVersion

_ALL = [
    "events.create",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.postprocess",
    "events.archive",
    "events.reactivate",
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
    os.environ["BBZ_JWT_SECRET"] = "e2e-archive-secret-at-least-32-bytes-please!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_REACTIVATION_COOLDOWN_SECONDS"] = "0"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    os.environ.pop("BBZ_REACTIVATION_COOLDOWN_SECONDS", None)
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


async def _audit_actions(s: AsyncSession, eid: str) -> list[str]:
    rows = (
        await s.execute(
            select(AuditEvent.action)
            .where(AuditEvent.target_type == "event", AuditEvent.target_id == eid)
            .order_by(AuditEvent.occurred_at_utc.asc(), AuditEvent.id.asc())
        )
    ).scalars()
    return list(rows)


async def _domain_types(s: AsyncSession, eid: str) -> list[str]:
    rows = (
        await s.execute(
            select(DomainEvent.event_type)
            .where(DomainEvent.aggregate_id == eid)
            .order_by(DomainEvent.event_seq.asc())
        )
    ).scalars()
    return list(rows)


async def test_archive_postprocess_export_reactivate_lifecycle(env: tuple) -> None:
    client, s = env
    await _make_user(s, "leitstelle", _ALL)
    await _login(client, "leitstelle")

    # -- 1. an event is worked and a workflow step completed -------------------
    async with s.begin():
        tpl = WorkflowTemplate(key="brand", name="brand")
        s.add(tpl)
        await s.flush()
        s.add(
            WorkflowTemplateVersion(
                template_id=tpl.id, version_no=1, lifecycle="published", definition=_GRAPH
            )
        )

    eid = (
        await client.post(
            "/api/v1/events",
            json={
                "title": "Brandmeldeanlage Halle 7",
                "priority": "critical",
                "description": "BMA",
            },
            headers=_cmd(),
        )
    ).json()["id"]
    for verb, ver in (("accept", 1), ("acknowledge", 2), ("open", 3)):
        assert (
            await client.post(f"/api/v1/events/{eid}/{verb}", headers=_cmd(version=ver))
        ).status_code == 200
    assert (
        await client.post(f"/api/v1/events/{eid}/workflow", json={"template_key": "brand"})
    ).status_code == 201
    assert (
        await client.post(
            f"/api/v1/events/{eid}/workflow/steps/m/complete", json={"result": {"ok": True}}
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/events/{eid}/notes", json={"body": "Feuerwehr vor Ort"}, headers=_cmd()
        )
    ).status_code == 201

    # -- 2. archive ----------------------------------------------------------
    arch = await client.post(
        f"/api/v1/events/{eid}/archive", json={"reason": "Einsatz beendet"}, headers=_cmd(version=4)
    )
    assert arch.status_code == 200 and arch.json()["status"] == "archived"
    assert eid not in [
        i["id"] for i in (await client.get("/api/v1/events?queue=active")).json()["items"]
    ]

    # -- 3. view the archived detail — full depth ---------------------------
    detail = (await client.get(f"/api/v1/events/{eid}/archive-detail")).json()
    assert detail["event"]["status"] == "archived"
    assert [n["body"] for n in detail["event"]["notes"]] == ["Feuerwehr vor Ort"]
    assert len(detail["workflows"]) == 1 and detail["workflows"][0]["status"] in {
        "running",
        "completed",
    }
    assert detail["domain_events"][-1]["event_type"] == "EVENT_ARCHIVED"

    # -- 4. post-processing note (added, then edited) on the archived event -
    pp = await client.post(
        f"/api/v1/events/{eid}/notes",
        json={"body": "Nachbericht v1", "kind": "postprocess"},
        headers=_cmd(),
    )
    assert pp.status_code == 201
    pp_id = pp.json()["note_id"]
    assert (
        await client.patch(
            f"/api/v1/events/{eid}/notes/{pp_id}", json={"body": "Nachbericht v2"}, headers=_cmd()
        )
    ).status_code == 200
    threads = (await client.get(f"/api/v1/events/{eid}/notes")).json()["notes"]
    pp_thread = next(t for t in threads if t["thread_id"] == pp_id)
    assert pp_thread["version"] == 2 and pp_thread["body"] == "Nachbericht v2"
    assert [h["body"] for h in pp_thread["history"]] == ["Nachbericht v1"]

    # -- 5. export the complete bundle ------------------------------------
    bundle = (await client.get(f"/api/v1/events/{eid}/export")).json()
    assert bundle["bundle_version"] == "1"
    assert bundle["event"]["id"] == eid
    assert {"EVENT_ARCHIVED", "ACTION_STEP_COMPLETED"} <= {
        a["action"] for a in bundle["audit_entries"]
    }
    assert [d["event_type"] for d in bundle["domain_events"]] == await _domain_types(s, eid)

    # -- 6. reactivation only after the two-step confirmation --------------
    no_token = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "Rückfrage"},
        headers=_cmd(version=5),
    )
    assert no_token.status_code == 422  # no path reactivates without the token
    token = (await client.post(f"/api/v1/events/{eid}/reactivation-intent")).json()["token"]
    re_ok = await client.post(
        f"/api/v1/events/{eid}/reactivate",
        json={"confirm": True, "reason": "Rückfrage Kripo", "token": token},
        headers=_cmd(version=5),
    )
    assert re_ok.status_code == 200 and re_ok.json()["status"] == "opened"
    assert eid in [
        i["id"] for i in (await client.get("/api/v1/events?queue=active")).json()["items"]
    ]

    # -- 7. audit trail is complete and ordered --------------------------
    actions = await _audit_actions(s, eid)
    for expected in (
        "EVENT_ARCHIVED",
        "EVENT_NOTE_ADDED",
        "EVENT_NOTE_UPDATED",
        "EVENT_EXPORTED",
        "EVENT_REACTIVATED",
    ):
        assert expected in actions, f"{expected} missing from {actions}"
    assert actions.index("EVENT_ARCHIVED") < actions.index("EVENT_REACTIVATED")

    # -- 8. nothing was hard-deleted ------------------------------------
    note_rows = (
        await s.execute(
            select(func.count()).select_from(EventNote).where(EventNote.event_id == uuid.UUID(eid))
        )
    ).scalar_one()
    assert note_rows == 3  # work note + postprocess v1 (superseded) + v2
    types = await _domain_types(s, eid)
    assert types[0] == "EVENT_CREATED"
    assert types.count("EVENT_ARCHIVED") == 1  # from step 2; a second archive would add another
    assert "EVENT_REACTIVATED" in types
    # the pre-archive status history survived the archive + reactivation
    hist = [
        (h["from_status"], h["to_status"])
        for h in (await client.get(f"/api/v1/events/{eid}")).json()["status_history"]
    ]
    assert hist[:5] == [
        (None, "new"),
        ("new", "accepted"),
        ("accepted", "acknowledged"),
        ("acknowledged", "opened"),
        ("opened", "archived"),
    ]
    assert hist[-1] == ("archived", "opened")
