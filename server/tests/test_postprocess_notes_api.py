"""Post-processing notes: versioned, editable, audited, work on archived events (E20-04).

An edit never mutates a note — it appends a new version and marks the old one
superseded. Every add and every edit emits a domain event *and* an audit row.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.audit import AuditEvent
from bbz_core.infra.models.domain_events import DomainEvent
from bbz_core.infra.models.events import EventNote

_ALL = [
    "events.create",
    "events.accept",
    "events.acknowledge",
    "events.open",
    "events.archive",
    "events.postprocess",
    "events.view",
]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "postproc-notes-secret-at-least-32-bytes-ok!!"
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


async def _archived_event(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/v1/events", json={"title": "Weichenstörung", "priority": "medium"}, headers=_cmd()
    )
    eid = r.json()["id"]
    for verb, ver in (("accept", 1), ("acknowledge", 2), ("open", 3)):
        assert (
            await client.post(f"/api/v1/events/{eid}/{verb}", headers=_cmd(version=ver))
        ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/events/{eid}/archive",
            json={"reason": "Schicht Ende"},
            headers=_cmd(version=4),
        )
    ).status_code == 200
    return eid


async def _add(client: httpx.AsyncClient, eid: str, body: str, kind: str = "postprocess") -> str:
    r = await client.post(
        f"/api/v1/events/{eid}/notes", json={"body": body, "kind": kind}, headers=_cmd()
    )
    assert r.status_code == 201, r.text
    return r.json()["note_id"]


async def _edit(
    client: httpx.AsyncClient, eid: str, note_id: str, body: str, **kw: object
) -> httpx.Response:
    return await client.patch(
        f"/api/v1/events/{eid}/notes/{note_id}",
        json={"body": body},
        headers=_cmd(**kw),  # type: ignore[arg-type]
    )


async def test_postprocess_note_can_be_added_to_an_archived_event(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl", _ALL)
    await _login(client, "sl")
    eid = await _archived_event(client)

    nid = await _add(client, eid, "Bericht an Leitstelle")
    note = await s.get(EventNote, uuid.UUID(nid))
    assert note is not None and note.kind == "postprocess" and note.version == 1
    assert await _count(s, AuditEvent, "EVENT_NOTE_ADDED") == 1
    assert await _count(s, DomainEvent, "EVENT_NOTE_ADDED", col="event_type") == 1


async def test_edit_appends_a_version_and_keeps_the_old_one(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl2", _ALL)
    await _login(client, "sl2")
    eid = await _archived_event(client)
    nid = await _add(client, eid, "erste Fassung")

    r2 = await _edit(client, eid, nid, "zweite Fassung")
    assert r2.status_code == 200, r2.text
    r3 = await _edit(client, eid, nid, "dritte Fassung")
    assert r3.status_code == 200, r3.text

    # three rows exist; only the newest is current
    rows = (
        (
            await s.execute(
                select(EventNote)
                .where(EventNote.event_id == uuid.UUID(eid))
                .order_by(EventNote.version.asc())
            )
        )
        .scalars()
        .all()
    )
    assert [n.version for n in rows] == [1, 2, 3]
    assert [n.body for n in rows] == ["erste Fassung", "zweite Fassung", "dritte Fassung"]
    assert [n.superseded_by_id is None for n in rows] == [False, False, True]
    assert await _count(s, AuditEvent, "EVENT_NOTE_UPDATED") == 2
    assert await _count(s, DomainEvent, "EVENT_NOTE_UPDATED", col="event_type") == 2


async def test_notes_listing_shows_current_plus_history(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl3", _ALL)
    await _login(client, "sl3")
    eid = await _archived_event(client)
    nid = await _add(client, eid, "v1 text")
    await _edit(client, eid, nid, "v2 text")
    await _edit(client, eid, nid, "v3 text")

    listed = (await client.get(f"/api/v1/events/{eid}/notes")).json()["notes"]
    assert len(listed) == 1
    thread = listed[0]
    assert thread["version"] == 3 and thread["body"] == "v3 text"
    assert thread["thread_id"] == nid
    assert [(h["version"], h["body"]) for h in thread["history"]] == [
        (1, "v1 text"),
        (2, "v2 text"),
    ]

    # the plain event detail shows only the current version
    detail = (await client.get(f"/api/v1/events/{eid}")).json()
    assert [n["body"] for n in detail["notes"]] == ["v3 text"]
    assert detail["notes"][0]["version"] == 3


async def test_editing_via_the_original_id_targets_the_current_tip(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl4", _ALL)
    await _login(client, "sl4")
    eid = await _archived_event(client)
    nid = await _add(client, eid, "original")
    # every edit references the same stable id (the thread root) and still walks forward
    assert (await _edit(client, eid, nid, "geaendert")).status_code == 200
    assert (await _edit(client, eid, nid, "nochmal geaendert")).status_code == 200

    thread = (await client.get(f"/api/v1/events/{eid}/notes")).json()["notes"][0]
    assert thread["version"] == 3 and thread["body"] == "nochmal geaendert"
    assert [h["version"] for h in thread["history"]] == [1, 2]


async def test_edit_is_idempotent_on_command_id(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl5", _ALL)
    await _login(client, "sl5")
    eid = await _archived_event(client)
    nid = await _add(client, eid, "start")

    cid = uuid.uuid4()
    first = await _edit(client, eid, nid, "final", command_id=cid)
    second = await _edit(client, eid, nid, "final", command_id=cid)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert await _count(s, DomainEvent, "EVENT_NOTE_UPDATED", col="event_type") == 1


async def test_edit_with_unchanged_body_is_422(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl6", _ALL)
    await _login(client, "sl6")
    eid = await _archived_event(client)
    nid = await _add(client, eid, "gleich")
    assert (await _edit(client, eid, nid, "gleich")).status_code == 422


async def test_edit_on_a_foreign_event_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl7", _ALL)
    await _login(client, "sl7")
    eid = await _archived_event(client)
    nid = await _add(client, eid, "x")
    other = await _archived_event(client)
    assert (await _edit(client, other, nid, "y")).status_code == 404


async def test_edit_requires_postprocess_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "sl8", _ALL)
    await _login(client, "sl8")
    eid = await _archived_event(client)
    nid = await _add(client, eid, "x")

    await _make_user(s, "peon", ["events.create", "events.view"])
    await _login(client, "peon")
    assert (await _edit(client, eid, nid, "y")).status_code == 403


async def _count(s: AsyncSession, model: type, value: str, *, col: str = "action") -> int:
    return (
        await s.execute(select(func.count()).select_from(model).where(getattr(model, col) == value))
    ).scalar_one()
