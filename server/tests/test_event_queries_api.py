"""GET /events (queue / list / detail) — E03-12."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.infra.models.events import Event

_PERMS = ["events.create", "events.view"]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "queries-test-secret-at-least-32-bytes-oka!!"
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


async def _create(client: httpx.AsyncClient, title: str, priority: str) -> str:
    r = await client.post(
        "/api/v1/events",
        json={"title": title, "priority": priority},
        headers={"X-Command-Id": str(uuid.uuid4())},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def test_work_queue_excludes_archived_and_sorts_by_priority(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op", _PERMS)
    await _login(client, "op")

    await _create(client, "niedrig", "low")
    await _create(client, "kritisch", "critical")
    await _create(client, "hoch", "high")
    s.add(Event(title="alt-archiviert", priority="critical", status="archived"))
    await s.commit()

    r = await client.get("/api/v1/events?queue=active")
    assert r.status_code == 200
    body = r.json()
    assert body["next_cursor"] is None
    titles = [i["title"] for i in body["items"]]
    assert "alt-archiviert" not in titles
    assert titles == ["kritisch", "hoch", "niedrig"]


async def test_list_includes_archived_and_paginates_stably(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op2", _PERMS)
    await _login(client, "op2")

    ids = [await _create(client, f"e{n}", "medium") for n in range(3)]

    page1 = (await client.get("/api/v1/events?limit=2")).json()
    assert [i["id"] for i in page1["items"]] == [ids[2], ids[1]]  # newest first
    assert page1["next_cursor"]

    # an insert between page fetches must not shift page 2
    await _create(client, "zwischen", "medium")

    page2 = (await client.get(f"/api/v1/events?limit=2&cursor={page1['next_cursor']}")).json()
    assert [i["id"] for i in page2["items"]] == [ids[0]]
    assert page2["next_cursor"] is None


async def test_detail_returns_history_assignee_notes(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op3", _PERMS)
    await _login(client, "op3")
    eid = await _create(client, "detailtest", "high")

    r = await client.get(f"/api/v1/events/{eid}")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == eid
    assert d["assignee_id"] is None
    assert d["notes"] == []
    assert [(h["from_status"], h["to_status"]) for h in d["status_history"]] == [(None, "new")]


async def test_detail_unknown_event_is_404(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op4", _PERMS)
    await _login(client, "op4")
    r = await client.get(f"/api/v1/events/{uuid.uuid4()}")
    assert r.status_code == 404


async def test_queries_require_events_view(env: tuple) -> None:
    client, s = env
    await _make_user(s, "op5", ["events.create"])
    await _login(client, "op5")
    assert (await client.get("/api/v1/events")).status_code == 403
    assert (await client.get("/api/v1/events?queue=active")).status_code == 403
