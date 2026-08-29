"""POST /events/{id}/notes + GET /events/{id}/export — E03-16."""

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

_ALL = [
    "events.create",
    "events.accept",
    "events.postprocess",
    "events.export",
    "events.view",
]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "notes-test-secret-at-least-32-bytes-okayyy!!"
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


def _cmd(command_id: uuid.UUID | None = None, *, version: int | None = None) -> dict[str, str]:
    h = {"X-Command-Id": str(command_id or uuid.uuid4())}
    if version is not None:
        h["X-Expected-Version"] = str(version)
    return h


async def _create(client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/api/v1/events", json={"title": "Stellwerkstörung", "priority": "high"}, headers=_cmd()
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_add_note_emits_domain_event(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _ALL)
    await _login(client, "op")
    eid = await _create(client)

    r = await client.post(
        f"/api/v1/events/{eid}/notes", json={"body": "Techniker verständigt"}, headers=_cmd()
    )
    assert r.status_code == 201, r.text
    assert r.json()["note_id"]

    rows = (
        (
            await s.execute(
                select(DomainEvent).where(
                    DomainEvent.aggregate_id == eid,
                    DomainEvent.event_type == "EVENT_NOTE_ADDED",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].payload["body"] == "Techniker verständigt"
    assert rows[0].payload["kind"] == "work"


async def test_add_note_is_idempotent(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _ALL)
    await _login(client, "op2")
    eid = await _create(client)

    cid = uuid.uuid4()
    body = {"body": "einmalige Notiz"}
    first = await client.post(f"/api/v1/events/{eid}/notes", json=body, headers=_cmd(cid))
    second = await client.post(f"/api/v1/events/{eid}/notes", json=body, headers=_cmd(cid))
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    count = (
        await s.execute(
            select(func.count())
            .select_from(DomainEvent)
            .where(DomainEvent.event_type == "EVENT_NOTE_ADDED")
        )
    ).scalar_one()
    assert count == 1


async def test_add_note_unknown_event_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", _ALL)
    await _login(client, "op3")
    r = await client.post(
        f"/api/v1/events/{uuid.uuid4()}/notes", json={"body": "x"}, headers=_cmd()
    )
    assert r.status_code == 404


async def test_add_note_rejects_postprocess_kind(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4", _ALL)
    await _login(client, "op4")
    eid = await _create(client)
    r = await client.post(
        f"/api/v1/events/{eid}/notes",
        json={"body": "x", "kind": "postprocess"},
        headers=_cmd(),
    )
    assert r.status_code == 422


async def test_add_note_requires_postprocess_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5", ["events.create"])
    await _login(client, "op5")
    eid = await _create(client)
    r = await client.post(f"/api/v1/events/{eid}/notes", json={"body": "x"}, headers=_cmd())
    assert r.status_code == 403


async def test_export_is_complete_and_seq_ordered_and_audited(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op6", _ALL)
    await _login(client, "op6")
    eid = await _create(client)
    await client.post(f"/api/v1/events/{eid}/accept", headers=_cmd(version=1))
    await client.post(f"/api/v1/events/{eid}/notes", json={"body": "Notiz A"}, headers=_cmd())

    r = await client.get(f"/api/v1/events/{eid}/export")
    assert r.status_code == 200, r.text
    bundle = r.json()
    assert bundle["event"]["id"] == eid
    assert [(h["from_status"], h["to_status"]) for h in bundle["event"]["status_history"]] == [
        (None, "new"),
        ("new", "accepted"),
    ]
    assert [n["body"] for n in bundle["event"]["notes"]] == ["Notiz A"]

    seqs = [d["event_seq"] for d in bundle["domain_events"]]
    assert seqs == sorted(seqs)
    assert [d["event_type"] for d in bundle["domain_events"]] == [
        "EVENT_CREATED",
        "EVENT_ACCEPTED",
        "EVENT_NOTE_ADDED",
    ]

    audited = (
        await s.execute(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "EVENT_EXPORTED", AuditEvent.target_id == eid)
        )
    ).scalar_one()
    assert audited == 1


async def test_export_requires_export_permission(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op7", ["events.create", "events.view"])
    await _login(client, "op7")
    eid = await _create(client)
    assert (await client.get(f"/api/v1/events/{eid}/export")).status_code == 403
